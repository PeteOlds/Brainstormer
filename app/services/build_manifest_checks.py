"""Deterministic checks for generated build manifests.

These run before a preview is stored and again before files are written.
They are intentionally cheap and mechanical: a local model cannot talk its
way past a line cap or a placeholder stub.
"""

import re

MAX_LINES = 300
# Data/config files can legitimately be long; source files cannot.
LONG_FILE_EXTENSIONS = {".json", ".lock", ".txt", ".md", ".yml", ".yaml", ".csv", ".svg"}
PLACEHOLDER_RE = re.compile(
    r"\b(TODO|FIXME|PLACEHOLDER|STUB|XXX)\b|NotImplementedError|"
    r"#\s*\.\.\.\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class BuildManifestError(ValueError):
    """Raised when a manifest fails a deterministic check."""


def check_manifest_files(files: list[dict], require_agents_md: bool = False) -> list[str]:
    """Return human-readable problems; empty list means the manifest is OK."""
    problems: list[str] = []
    paths: list[str] = []

    for entry in files or []:
        if not isinstance(entry, dict):
            problems.append("manifest contains a non-object file entry")
            continue
        path = str(entry.get("path") or "").strip()
        content = entry.get("content")
        if not path:
            problems.append("manifest contains a file with no path")
            continue
        paths.append(path)
        if path.startswith("/") or path.startswith("~") or ".." in path.split("/"):
            problems.append(f"unsafe file path: {path}")
            continue
        if not isinstance(content, str) or not content:
            problems.append(f"empty content: {path}")
            continue
        lines = content.splitlines()
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if suffix not in LONG_FILE_EXTENSIONS and len(lines) > MAX_LINES:
            problems.append(f"{path} has {len(lines)} lines (max {MAX_LINES})")
        if PLACEHOLDER_RE.search(content):
            problems.append(f"{path} contains a TODO/FIXME/placeholder marker")

    if require_agents_md and "AGENTS.md" not in paths:
        problems.append("AGENTS.md is missing from the build manifest")
    return problems


def ensure_manifest_files(files: list[dict], require_agents_md: bool = False) -> None:
    """Raise BuildManifestError with all problems joined into one message."""
    problems = check_manifest_files(files, require_agents_md=require_agents_md)
    if problems:
        raise BuildManifestError("; ".join(problems))
