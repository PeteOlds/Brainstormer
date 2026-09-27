"""Runtime discovery of opencode skills and guideline docs.

Skills are opencode skills (``*/SKILL.md`` with YAML frontmatter holding
at least ``name`` and ``description``), discovered under the directories
in ``SKILLS_DIRS`` (os.pathsep-separated). The worker/web containers can
only see host skill dirs through explicit read-only volume mounts.

Guidelines are ``*.md`` files under ``GUIDELINES_DIR`` (default
``<repo>/guidelines``, i.e. ``/app/guidelines`` in containers).

Nothing is cached and nothing touches the DB: sets are small and the
admin's add/remove must show up immediately. Reads are traversal-safe
(names are resolved and confined to the known directories).
"""
import os
import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def skill_dirs() -> list:
    raw = os.getenv("SKILLS_DIRS", "")
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]


def guidelines_dir() -> Path:
    return Path(os.getenv("GUIDELINES_DIR", str(_repo_root() / "guidelines")))


def _parse_frontmatter(text: str) -> dict:
    """Parse the leading YAML frontmatter block (simple key: value lines)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    current = None
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            current = m.group(1)
            out[current] = m.group(2).strip().strip("'\"")
        elif current and line[:1] in (" ", "\t"):
            out[current] += " " + line.strip().strip("'\"")
    return out


def list_skills() -> list:
    """All discoverable opencode skills: name, description, source dir."""
    found = []
    for base in skill_dirs():
        if not base.is_dir():
            continue
        for skill_file in sorted(base.glob("*/SKILL.md")):
            try:
                meta = _parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            name = meta.get("name") or skill_file.parent.name
            found.append({
                "name": name,
                "description": meta.get("description", ""),
                "source": str(base),
            })
    return found


def list_guidelines() -> list:
    """Guideline docs: file-based title, size for budgeting."""
    base = guidelines_dir()
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.glob("*.md")):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out.append({
            "name": path.stem,
            "file": path.name,
            "size": size,
        })
    return out


def read_skill_body(name: str) -> str | None:
    """Full SKILL.md body for a discovered skill name, else None."""
    for base in skill_dirs():
        if not base.is_dir():
            continue
        for skill_file in base.glob("*/SKILL.md"):
            try:
                meta = _parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if (meta.get("name") or skill_file.parent.name) == name:
                try:
                    return skill_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
    return None


def read_guideline(name: str) -> str | None:
    """Guideline body by file stem (no traversal: stem only, fixed dir)."""
    base = guidelines_dir()
    if not base.is_dir() or "/" in name or name.startswith("."):
        return None
    path = (base / f"{name}.md").resolve()
    try:
        base_resolved = base.resolve()
    except OSError:
        return None
    if base_resolved not in path.parents:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
