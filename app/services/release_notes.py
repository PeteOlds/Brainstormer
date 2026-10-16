"""Write release notes into the docs directory as markdown.

The Scale tab shows the same text; this is the durable, committable copy
that lives with the project documentation. Directory defaults to
docs/release-notes (override with RELEASE_NOTES_DIR).
"""

import os
import re
from pathlib import Path


def release_notes_dir() -> Path:
    raw = os.getenv("RELEASE_NOTES_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    # app/services/release_notes.py -> project root
    return Path(__file__).resolve().parent.parent.parent / "docs" / "release-notes"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "release"


def release_notes_filename(release, parent) -> str:
    parts = []
    parent_ref = getattr(parent, "reference_code", "") if parent else ""
    if parent_ref:
        parts.append(parent_ref)
    parts.append(release.name or "release")
    return "-".join(_slug(p) for p in parts) + ".md"


def release_notes_path(release, parent) -> Path:
    return release_notes_dir() / release_notes_filename(release, parent)


def write_release_notes_file(release, parent) -> Path | None:
    """Persist release.notes as markdown. Returns the path (None on failure).

    Never raises: a docs write must not fail the release completion.
    """
    notes = (release.notes or "").strip()
    if not notes:
        return None
    try:
        path = release_notes_path(release, parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = f"# {release.name}\n\n{notes}\n" if release.name else notes
        path.write_text(body, encoding="utf-8")
        return path
    except OSError:
        return None
