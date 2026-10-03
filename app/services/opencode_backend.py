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
def _run_dir(workspace: str) -> Iterator[str]:
    """Yield the working directory for a run, cleaning up sandboxes."""
    if (workspace or "sandbox") == "repo":
        repo = _workspace_dir()
        if not repo or not os.path.isdir(repo):
            raise ProviderError(
                "OpenCode repo workspace is not configured "
                "(set OPENCODE_WORKSPACE_DIR).",
                retryable=False,
            )
        yield repo
        return
    tmp = tempfile.mkdtemp(prefix="brainstormer-opencode-")
    try:
        _write_sandbox_agent(tmp, _sandbox_agent_name())
        yield tmp
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


def opencode_generate(
    model: str,
    prompt_text: str,
    system: str | None = None,
    options: dict | None = None,
    timeout: float | None = None,
    json_mode: bool = True,
    workspace: str = "sandbox",
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

    argv = [resolved, "run", "--format", "json", "--model", model]
    agent = _sandbox_agent_name()
    if (workspace or "sandbox") == "sandbox" and agent:
        argv += ["--agent", agent]
    argv.append(_compose_message(prompt_text, system))

    env = _clean_env()
    started = time.monotonic()
    with _run_dir(workspace) as cwd:
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
