"""Code-build file writes: confinement, manifest application, cleanup.

Every path a BUILD_CODE run touches must resolve under one of the
``OPENCODE_BUILD_ROOTS`` directories (os.pathsep-separated, worker-side).
Fail closed: empty roots mean no target can be registered and no file is
written. Symlinks are resolved before the prefix check so ``..`` games
and link escapes are refused, not just normalized.
"""

import os
import socket
from typing import Any

import structlog

logger = structlog.get_logger()


class BuildError(Exception):
    """Unsafe or impossible build target/file. Never raised to Celery."""


def build_roots() -> list:
    """Configured build roots, resolved. Empty when unconfigured."""
    def _config(key: str, default=None):
        from flask import current_app

        try:
            return current_app.config.get(key, default)
        except RuntimeError:
            return os.getenv(key, default)

    raw = _config("OPENCODE_BUILD_ROOTS", "") or ""
    roots = []
    for part in raw.split(os.pathsep):
        part = (part or "").strip()
        if not part:
            continue
        try:
            resolved = os.path.realpath(os.path.abspath(part))
        except OSError:
            continue
        roots.append(resolved)
    return roots


def server_build_roots() -> list:
    """Host-side twins of build_roots(), same order, unresolved.

    Users paste run commands into a shell on the host, where container
    paths like /app/... do not exist. Unset entries (or a shorter list)
    leave those roots untranslated; never raises.
    """

    def _config(key: str, default=None):
        from flask import current_app

        try:
            return current_app.config.get(key, default)
        except RuntimeError:
            return os.getenv(key, default)

    raw = _config("OPENCODE_SERVER_BUILD_ROOTS", "") or ""
    return [
        os.path.normpath(part)
        for part in ((p or "").strip() for p in raw.split(os.pathsep))
        if part
    ]


def server_path(container_path: str) -> str:
    """Translate a worker-visible path to the host path for pasted commands.

    Longest-prefix match of build_roots() against the host twins; returns
    the input unchanged when nothing matches (fail open: a container path
    the user can ask about beats a mangled one).
    """
    cand = (container_path or "").strip()
    if not cand:
        return cand
    norm = os.path.normpath(cand)
    croots = build_roots()
    sroots = server_build_roots()
    best = None
    for croot, sroot in zip(croots, sroots):
        if not sroot:
            continue
        if norm == croot or norm.startswith(croot + os.sep):
            if best is None or len(croot) > len(best[0]):
                best = (croot, sroot)
    if best is None:
        return cand
    croot, sroot = best
    rest = norm[len(croot) :].lstrip(os.sep)
    return sroot if not rest else sroot + os.sep + rest


def container_path(host_path: str) -> str:
    """Inverse of server_path: host path back to the worker-visible path.

    Supervised processes run inside worker containers, where host paths
    like /mnt/... do not exist — everything the runner touches (cwd,
    venv, log files) must go through this. Same longest-prefix rule,
    same fail-open passthrough.
    """
    cand = (host_path or "").strip()
    if not cand:
        return cand
    norm = os.path.normpath(cand)
    croots = build_roots()
    sroots = server_build_roots()
    best = None
    for croot, sroot in zip(croots, sroots):
        if not sroot:
            continue
        if norm == sroot or norm.startswith(sroot + os.sep):
            if best is None or len(sroot) > len(best[0]):
                best = (sroot, croot)
    if best is None:
        return cand
    sroot, croot = best
    rest = norm[len(sroot) :].lstrip(os.sep)
    return croot if not rest else croot + os.sep + rest


def _confine(resolved: str, roots: list) -> str:
    for root in roots:
        if resolved == root or resolved.startswith(root + os.sep):
            return resolved
    raise BuildError(
        "Path is outside the configured build roots "
        f"({', '.join(roots) if roots else 'none configured'})."
    )


def resolve_target_path(path: str) -> str:
    """Validate a candidate target root. Returns the resolved path."""
    candidate = (path or "").strip()
    if not candidate:
        raise BuildError("Build target path is required.")
    if not os.path.isabs(candidate):
        raise BuildError("Build target path must be absolute.")
    try:
        resolved = os.path.realpath(os.path.abspath(candidate))
    except OSError as exc:
        raise BuildError(f"Build target path is unusable: {exc}") from exc
    _confine(resolved, build_roots())
    if not os.path.isdir(resolved):
        raise BuildError("Build target path is not an existing directory.")
    return resolved


def resolve_target(target: Any) -> str:
    """Re-validate a registered target at write time (roots may change)."""
    return resolve_target_path(target.path)


def ensure_target_path(path: str) -> str:
    """Validate a candidate root and create it (registration time).

    Confinement is checked before anything is created, so a bad path can
    never mkdir outside the roots. Re-checks directory-ness afterwards.
    """
    candidate = (path or "").strip()
    if not candidate:
        raise BuildError("Build target path is required.")
    if not os.path.isabs(candidate):
        raise BuildError("Build target path must be absolute.")
    roots = build_roots()
    try:
        resolved = os.path.realpath(os.path.abspath(candidate))
    except OSError as exc:
        raise BuildError(f"Build target path is unusable: {exc}") from exc
    _confine(resolved, roots)
    existed = os.path.isdir(resolved)
    chain = []
    if not existed:
        # Remember every level makedirs is about to create: a nested
        # path leaves several root-owned dirs behind, not just the leaf.
        probe = resolved
        while not os.path.isdir(probe):
            chain.append(probe)
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
    try:
        os.makedirs(resolved, exist_ok=True)
    except OSError as exc:
        raise BuildError(f"Build target path cannot be created: {exc}") from exc
    if chain:
        # Registration runs as root while task workers run as the app
        # user: root-owned target dirs fail every later file write with
        # EACCES (seen live on IDEA-9603). Hand created levels to the
        # first existing ancestor's owner — never touch pre-existing
        # dirs, and never fail registration if a chown is refused.
        try:
            st = os.stat(os.path.dirname(chain[-1]))
            for level in chain:
                if os.path.isdir(level):
                    os.chown(level, st.st_uid, st.st_gid)
        except OSError as exc:
            logger.warning(
                "build_target_chown_skipped", path=resolved, error=str(exc)[:200]
            )
    if not os.path.isdir(resolved):
        raise BuildError("Build target path is not an existing directory.")
    return resolved


def join_target_path(root: str, rel_path: str) -> str:
    """Join a manifest path under root, refusing escapes."""
    cleaned = str(rel_path or "").replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise BuildError(f"Refusing unsafe file path: {rel_path!r}")
    full = os.path.realpath(os.path.join(root, *parts))
    return _confine(full, [root])


# Repo context is a prompt budget, not a backup: enough to let the model
# extend an existing app without crowding out the design document.
SNAPSHOT_MAX_FILES = 40
SNAPSHOT_MAX_CHARS = 30000
SNAPSHOT_MAX_FILE_CHARS = 12000

_SNAPSHOT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".venv-local",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "certs",
    "logs",
}

_SNAPSHOT_TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".json",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sql",
    ".sh",
    ".bash",
    ".vue",
    ".svelte",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".env",
}

# Files a model must see before changing an app: how it starts, what it
# depends on, and what it says it does.
_SNAPSHOT_PRIORITY = (
    "readme.md",
    "readme.txt",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "procfile",
    "makefile",
    "app.py",
    "main.py",
    "server.py",
    "index.html",
)


def existing_repo_snapshot(
    root: str,
    max_files: int = SNAPSHOT_MAX_FILES,
    max_chars: int = SNAPSHOT_MAX_CHARS,
) -> str:
    """Text snapshot of an existing build repo, for BUILD_CODE context.

    Returns '' when the root has no readable text files. Skips VCS data,
    virtualenvs, dependency trees and build output, plus binaries and
    oversized files. Deterministic ordering keeps prompts cache-friendly.
    Never raises: a context problem must not block a build.
    """
    base = (root or "").strip()
    if not base or not os.path.isdir(base):
        return ""
    candidates = []
    try:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in _SNAPSHOT_SKIP_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                if name.startswith("."):
                    # Keep .gitignore/.env.example style files, drop swap
                    # and editor litter.
                    if name not in (".gitignore", ".dockerignore", ".env.example"):
                        continue
                ext = os.path.splitext(name)[1].lower()
                if ext not in _SNAPSHOT_TEXT_SUFFIXES:
                    continue
                full = os.path.join(dirpath, name)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if size > SNAPSHOT_MAX_FILE_CHARS * 4:
                    continue
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                candidates.append((rel, full))
    except OSError as exc:
        logger.warning("repo_snapshot_walk_failed", path=base, error=str(exc)[:200])
        return ""

    def _rank(item):
        rel, _full = item
        name = rel.rsplit("/", 1)[-1].lower()
        try:
            priority = _SNAPSHOT_PRIORITY.index(name)
        except ValueError:
            priority = len(_SNAPSHOT_PRIORITY)
        # Shallow files first: they are the app's entry points.
        depth = rel.count("/")
        return (priority, depth, rel)

    candidates.sort(key=_rank)
    chunks = []
    used = 0
    shown = 0
    skipped_large = 0
    for rel, full in candidates:
        if shown >= max_files or used >= max_chars:
            break
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(SNAPSHOT_MAX_FILE_CHARS + 1)
        except OSError:
            continue
        if len(text) > SNAPSHOT_MAX_FILE_CHARS:
            text = text[:SNAPSHOT_MAX_FILE_CHARS].rstrip() + "\n… (truncated)"
            skipped_large += 1
        block = f"--- {rel} ---\n{text.rstrip()}\n"
        if used + len(block) > max_chars:
            break
        chunks.append(block)
        used += len(block)
        shown += 1
    if not chunks:
        return ""
    header = (
        "### EXISTING PROJECT FILES (the app this build extends)\n"
        "These files are already in the build repo. Preserve their working "
        "behaviour and routes. Return only the files you add or change, "
        "with their COMPLETE contents; do not drop existing features."
    )
    note = ""
    if skipped_large:
        note = f"\n({skipped_large} large file(s) truncated to keep the prompt in budget.)"
    return header + note + "\n\n" + "\n".join(chunks)


def write_manifest(root: str, files: list) -> tuple[list, list]:
    """Write manifest files under root. Returns (written, skipped).

    ``written`` is ``[{path, bytes}]`` (repo-relative paths); ``skipped``
    is ``[{path, reason}]``. Raises BuildError on the first refusal (I/O
    errors included) after removing anything already written, so a failed
    build never leaves a half-written tree behind.
    """
    written_paths: list = []
    written: list = []
    skipped: list = []
    try:
        for entry in files or []:
            rel = entry.get("path") if isinstance(entry, dict) else None
            content = entry.get("content") if isinstance(entry, dict) else None
            if not rel or content is None:
                skipped.append({"path": str(rel), "reason": "empty entry"})
                continue
            full = join_target_path(root, rel)
            parent = os.path.dirname(full)
            os.makedirs(parent, exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)
            written_paths.append(full)
            written.append(
                {
                    "path": os.path.relpath(full, root),
                    "bytes": len(content.encode("utf-8")),
                }
            )
    except BuildError:
        for path in written_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    except OSError as exc:
        for path in written_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise BuildError(f"Write failed, partial files removed: {exc}") from exc
    return written, skipped


def port_in_use(port: int) -> bool:
    """True when something on this host already holds ``port``.

    Workers run on the host network, so a bind test here reflects the
    machine the built app will run on. Both checks matter: connect_ex
    catches listeners, bind catches reservations that are not (yet)
    accepting. The probe bind sets SO_REUSEADDR so a just-stopped
    server's lingering TIME_WAIT sockets do not read as busy — a real
    listener still fails the bind, and servers (uvicorn included) set
    the same option, so the verdict matches what a fresh start can do.
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if not 1 <= port <= 65535:
        return False
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return True
    except OSError:
        pass
    finally:
        probe.close()
    binder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        binder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        binder.bind(("0.0.0.0", port))
    except OSError:
        return True
    finally:
        binder.close()
    return False


def allocate_port(preferred: int, max_tries: int = 25) -> tuple[int, bool]:
    """Return a free port, preferring ``preferred``.

    Scans upward (skipping privileged ports) and returns
    ``(port, changed)``. Never raises: if the whole range is busy the
    preferred port comes back and the caller records the conflict.
    """
    try:
        base = int(preferred)
    except (TypeError, ValueError):
        return 8000, True
    if base < 1024:
        base = 8080
    if base > 65535:
        base = 8080
    if not port_in_use(base):
        return base, False
    for candidate in range(base + 1, min(base + max_tries, 65535) + 1):
        if candidate < 1024:
            continue
        if not port_in_use(candidate):
            return candidate, True
    return base, True
