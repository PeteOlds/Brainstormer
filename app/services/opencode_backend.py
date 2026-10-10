"""OpenCode CLI provider (shared server identity).

Runs ``opencode run --format json`` as a subprocess and parses the
newline-delimited JSON event stream. No per-instance API key: the CLI
resolves its own credentials from the worker user's opencode auth store
(``~/.local/share/opencode/auth.json``), so no key ever enters argv,
prompts or logs.

Isolation: sandbox mode (default) runs in a throwaway empty directory
with a read-only agent definition, so the agent has no repo access.
Repo mode (Site-Admin opt-in per instance) runs in
``OPENCODE_WORKSPACE_DIR`` with the default agent.

Attach mode: when the instance config sets ``endpoint`` (or
``OPENCODE_SERVER_URL`` is set), the CLI runs against a remote opencode
server (``opencode run --attach <url> --dir <server-dir>``) instead of a
local server. Credentials then live on that server; the worker only needs
the CLI binary. Project-local ``--agent`` files are rejected by attached
servers, so attach mode skips ``--agent`` and isolates by directory only.
Sandbox dirs must exist on the *server*: the backend creates
``<OPENCODE_SANDBOX_ROOT>/<uuid>`` through the shared filesystem and
passes ``<OPENCODE_SERVER_SANDBOX_ROOT>/<uuid>`` as ``--dir`` (the two
roots must point at the same shared directory).

The subprocess gets a curated environment (PATH/HOME/locale plus
``OPENCODE_*``) so application secrets in the worker's env
(SECRET_KEY, FERNET_KEY, DATABASE_URL, provider keys) are never
inherited. Timeouts kill the whole process group.
"""

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

from app.services.llm_backends import GenerationResult, ProviderError

logger = structlog.get_logger()

SANDBOX_AGENT_NAME = "brainstormer-sandbox"

_SANDBOX_AGENT_BODY = """---
description: Read-only sandbox agent for Brainstormer generation.
mode: primary
tools:
  write: false
  edit: false
  bash: false
  read: false
---
You are a text-generation assistant. Return only the requested content,
in exactly the format the user asks for (JSON when a schema is given).
"""

# Environment keys the subprocess is allowed to inherit. Anything else
# (application secrets, provider keys) stays out of the child process.
_KEEP_ENV = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "TERM",
    "SHELL",
    "TMPDIR",
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
)


def _config(key: str, default: Any = None) -> Any:
    from flask import current_app

    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return os.getenv(key, default)


def _binary() -> str:
    return (_config("OPENCODE_BIN", "opencode") or "opencode").strip()


def _sandbox_agent_name() -> str:
    """Agent name for sandbox runs; empty disables ``--agent``.

    The escape hatch exists because OpenCode's free tier rejects any
    ``--agent`` flag ("free tier can only be used from within OpenCode").
    Paid providers accept it.
    """
    value = _config("OPENCODE_SANDBOX_AGENT", SANDBOX_AGENT_NAME)
    if value is None:
        value = SANDBOX_AGENT_NAME
    return str(value).strip()


def _workspace_dir() -> str:
    return (_config("OPENCODE_WORKSPACE_DIR", "") or "").strip()


def _attach_url(endpoint: str | None) -> str:
    """Remote opencode server URL, or "" for a local run.

    The per-instance ``endpoint`` wins; ``OPENCODE_SERVER_URL`` is the
    worker-wide fallback. Server basic-auth (if any) comes from
    ``OPENCODE_SERVER_USERNAME``/``OPENCODE_SERVER_PASSWORD`` env, which
    the curated environment already passes through.
    """
    return (endpoint or "").strip() or (
        _config("OPENCODE_SERVER_URL", "") or ""
    ).strip()


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sandbox_roots() -> tuple[str, str]:
    """(local_root, server_root) for attached sandbox runs.

    The backend creates per-run dirs under the local root (must be visible
    from this worker) and passes the same run under the server root as
    ``--dir``. The operator keeps both pointing at one shared directory
    (e.g. the bind-mounted repo). Unset server root fails loudly: without
    it the server would silently run in the wrong directory.
    """
    local = (_config("OPENCODE_SANDBOX_ROOT", "") or "").strip()
    if not local:
        local = os.path.join(_repo_root(), ".opencode-sandbox")
    server = (_config("OPENCODE_SERVER_SANDBOX_ROOT", "") or "").strip()
    return local, server


def _clean_env() -> dict:
    env = {key: os.environ[key] for key in _KEEP_ENV if key in os.environ}
    for key, value in os.environ.items():
        if key.startswith("OPENCODE_"):
            env[key] = value
    return env


def _write_sandbox_agent(directory: str, agent_name: str) -> None:
    if not agent_name:
        return
    agent_dir = os.path.join(directory, ".opencode", "agent")
    os.makedirs(agent_dir, exist_ok=True)
    with open(os.path.join(agent_dir, f"{agent_name}.md"), "w", encoding="utf-8") as fh:
        fh.write(_SANDBOX_AGENT_BODY)


@contextmanager
def _run_dir(workspace: str, attach_url: str = "") -> Iterator[tuple[str, str | None]]:
    """Yield ``(local_cwd, server_dir)`` for a run, cleaning up sandboxes.

    ``server_dir`` is the ``--dir`` value for attached runs, else None.
    Attached runs can never rely on the subprocess cwd (it is
    container-local and meaningless to the server), so they always get an
    explicit server-side directory. Local runs keep the previous behaviour.
    """
    workspace = workspace or "sandbox"
    if workspace == "repo":
        if attach_url:
            server = _workspace_dir()
            if not server:
                raise ProviderError(
                    "OpenCode repo workspace is not configured "
                    "(set OPENCODE_WORKSPACE_DIR to a server-side path).",
                    retryable=False,
                )
            tmp = tempfile.mkdtemp(prefix="brainstormer-opencode-")
            try:
                yield tmp, server
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            return
        repo = _workspace_dir()
        if not repo or not os.path.isdir(repo):
            raise ProviderError(
                "OpenCode repo workspace is not configured "
                "(set OPENCODE_WORKSPACE_DIR).",
                retryable=False,
            )
        yield repo, None
        return
    if attach_url:
        local_root, server_root = _sandbox_roots()
        if not server_root:
            raise ProviderError(
                "OpenCode attach mode needs OPENCODE_SERVER_SANDBOX_ROOT "
                "(server-side directory shared with this worker).",
                retryable=False,
            )
        name = f"brainstormer-{uuid.uuid4().hex}"
        local = os.path.join(local_root, name)
        os.makedirs(local, exist_ok=True)
        try:
            yield local, server_root.rstrip("/") + "/" + name
        finally:
            shutil.rmtree(local, ignore_errors=True)
        return
    tmp = tempfile.mkdtemp(prefix="brainstormer-opencode-")
    try:
        _write_sandbox_agent(tmp, _sandbox_agent_name())
        yield tmp, None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _kill_group(proc: subprocess.Popen) -> None:
    """Terminate the whole process group, escalating to SIGKILL."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()


def _error_from_event(error: dict) -> ProviderError:
    data = error.get("data") or {}
    message = data.get("message") or error.get("name") or "OpenCode error"
    status = data.get("statusCode")
    retryable = data.get("isRetryable")
    if retryable is None:
        retryable = status is None or (isinstance(status, int) and status >= 500)
    return ProviderError(str(message), retryable=bool(retryable), status=status)


def _parse_events(stdout: str) -> tuple[str, int, int, int]:
    """Parse the NDJSON stream.

    Returns ``(text, prompt_tokens, completion_tokens, cost_cents)``.
    ``cost`` from OpenCode is in USD; convert to integer cents.
    """
    chunks: list[str] = []
    prompt_tokens = completion_tokens = cost_cents = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        if etype == "text":
            part = event.get("part") or {}
            text = part.get("text")
            if text:
                chunks.append(str(text))
        elif etype == "error":
            raise _error_from_event(event.get("error") or {})
        elif etype == "step_finish":
            part = event.get("part") or {}
            tokens = part.get("tokens") or {}
            prompt_tokens += int(tokens.get("input") or 0)
            completion_tokens += int(tokens.get("output") or 0)
            try:
                cost_cents += int(round(float(part.get("cost") or 0) * 100))
            except (TypeError, ValueError):
                pass
    return "".join(chunks), prompt_tokens, completion_tokens, cost_cents


def _compose_message(prompt_text: str, system: str | None) -> str:
    if system:
        return f"{system.strip()}\n\n{prompt_text}"
    return prompt_text


# Short-lived catalog cache: the model dropdown hits this on every open.
# Keyed by server URL so tests and multi-server setups stay isolated.
_server_models_cache: dict = {}
SERVER_MODELS_TTL_SECONDS = 300


def list_server_models(
    server_url: str, provider: str = "opencode", timeout: float = 10.0
) -> list[str]:
    """Model slugs (`provider/id`) from an opencode server's catalog.

    Queries ``<server>/api/model`` (the same catalog the server's own UI
    uses) and keeps active, enabled entries for the requested provider.
    Returns [] when the server is unreachable or the catalog is unusable —
    callers fall back to free-text model entry. Results are cached briefly
    per server URL.
    """
    import time as _time

    import httpx

    base = (server_url or "").strip().rstrip("/")
    if not base:
        return []
    now = _time.monotonic()
    cached = _server_models_cache.get((base, provider))
    if cached and cached[0] > now:
        return list(cached[1])
    slugs: list[str] = []
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base}/api/model")
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        logger.warning("opencode_models_unreachable", server=base, error=str(exc)[:200])
        return []
    try:
        entries = (body.get("data") if isinstance(body, dict) else None) or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("providerID") != provider:
                continue
            if entry.get("status") not in (None, "active"):
                continue
            if entry.get("enabled") is False:
                continue
            model_id = str(entry.get("id") or "").strip()
            if model_id:
                slugs.append(f"{provider}/{model_id}")
    except Exception as exc:
        logger.warning("opencode_models_unparseable", server=base, error=str(exc)[:200])
        return []
    slugs = sorted(set(slugs))
    _server_models_cache[(base, provider)] = (now + SERVER_MODELS_TTL_SECONDS, slugs)
    return list(slugs)


def opencode_generate(
    model: str,
    prompt_text: str,
    system: str | None = None,
    options: dict | None = None,
    timeout: float | None = None,
    json_mode: bool = True,
    workspace: str = "sandbox",
    endpoint: str | None = None,
) -> GenerationResult:
    """Run one OpenCode generation and return the parsed result."""
    binary = _binary()
    resolved = shutil.which(binary)
    if resolved is None and os.path.isabs(binary) and os.path.exists(binary):
        resolved = binary
    if not resolved:
        raise ProviderError(
            f"OpenCode binary '{binary}' was not found on this worker.",
            retryable=False,
        )
    if not model:
        raise ProviderError("OpenCode requires a model.", retryable=False)

    if timeout is None:
        timeout = float(_config("OPENCODE_TIMEOUT", 1500) or 1500)

    attach_url = _attach_url(endpoint)
    workspace = workspace or "sandbox"
    argv = [resolved, "run", "--format", "json", "--model", model]
    server_dir: str | None = None
    if attach_url:
        argv += ["--attach", attach_url]
        agent = _sandbox_agent_name()
        if workspace == "sandbox" and agent:
            # Attached servers reject project-local --agent files, so
            # attach mode always uses the default agent (same reason the
            # free tier needs OPENCODE_SANDBOX_AGENT="").
            logger.info(
                "opencode_attach_no_agent",
                model=model,
                reason="attached servers reject project-local agents",
            )
    else:
        agent = _sandbox_agent_name()
        if workspace == "sandbox" and agent:
            argv += ["--agent", agent]
    argv.append(_compose_message(prompt_text, system))

    env = _clean_env()
    started = time.monotonic()
    attached = bool(attach_url)
    with _run_dir(workspace, attach_url) as (cwd, server_dir):
        if attach_url and server_dir:
            argv.insert(-1, "--dir")
            argv.insert(-1, server_dir)
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ProviderError(
                f"OpenCode binary '{binary}' could not be executed.", retryable=False
            ) from exc
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill_group(proc)
            logger.warning(
                "opencode_timeout",
                model=model,
                workspace=workspace,
                attached=attached,
                seconds=round(time.monotonic() - started, 1),
            )
            raise ProviderError(
                f"OpenCode run timed out after {timeout:.0f}s.", retryable=True
            ) from exc

    text, prompt_tokens, completion_tokens, cost_cents = _parse_events(stdout or "")
    if proc.returncode != 0 and not text:
        lines = (stderr or stdout or "").strip().splitlines()
        detail = lines[-1] if lines else f"exit code {proc.returncode}"
        raise ProviderError(f"OpenCode run failed: {detail}", retryable=True)
    if json_mode and not text:
        raise ProviderError("OpenCode returned no content.", retryable=True)

    logger.info(
        "opencode_ok",
        model=model,
        workspace=workspace,
        attached=attached,
        seconds=round(time.monotonic() - started, 1),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cents=cost_cents,
    )
    return GenerationResult(
        text=text,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cents=cost_cents,
    )
