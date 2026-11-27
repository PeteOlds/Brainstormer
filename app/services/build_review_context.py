"""Assemble the supporting material for a post-build release review.

The review is analysis only. This builder keeps the prompt local-model sized:
it summarises the design contract, the written manifest, the whole release
(parent + children) and a capped snapshot of the repo on disk.
"""

from typing import Any

from app.extensions import db
from app.models import Idea, Release, SecondaryActionResult
from app.services.build_service import existing_repo_snapshot
from app.services.design_contract import render_design_contract

DEFAULT_MAX_CHARS = 9000
SNAPSHOT_CHARS = 4000


def _current(action_type, idea_id):
    return SecondaryActionResult.query.filter_by(
        idea_id=idea_id, action_type=action_type, is_current=True
    ).first()


def _release_lines(idea):
    """One short line per idea in the release (parent first), capped."""
    lines: list[str] = []
    if not getattr(idea, "release_id", None):
        return lines
    release = db.session.get(Release, idea.release_id)
    if release is None:
        return lines
    parent = db.session.get(Idea, release.parent_idea_id)
    children = (
        Idea.query.filter_by(parent_id=release.parent_idea_id)
        .order_by(Idea.reference_code)
        .all()
    )
    for member in ([parent] if parent else []) + children:
        if member is None:
            continue
        build = _current("BUILD_CODE", member.id)
        data = (
            build.result_data if build and isinstance(build.result_data, dict) else {}
        )
        state = "written" if data.get("written") else "preview" if data else "no build"
        paths = [
            f.get("path") for f in (data.get("files") or []) if isinstance(f, dict)
        ]
        files = ", ".join(str(p) for p in paths[:4] if p is not None) or "none recorded"
        lines.append(
            f"- {member.reference_code} ({member.status}): {member.prompt_title} — "
            f"{state}; files: {files}"
        )
    return lines[:20]


def _manifest_lines(data):
    if not isinstance(data, dict):
        return []
    lines = []
    if data.get("summary"):
        lines.append("Summary: " + str(data["summary"])[:1200])
    paths = [f.get("path") for f in (data.get("files") or []) if isinstance(f, dict)]
    if paths:
        lines.append("Files: " + ", ".join(str(p) for p in paths[:25] if p is not None))
    tests = [t.get("name") for t in (data.get("tests") or []) if isinstance(t, dict)]
    if tests:
        lines.append("Checks: " + ", ".join(str(t) for t in tests[:12]))
    runbook = data.get("runbook")
    if isinstance(runbook, dict) and runbook.get("command"):
        lines.append("Run: " + str(runbook["command"])[:500])
    report = data.get("write_report") or []
    if report:
        lines.append("Write report: " + " | ".join(str(r) for r in report[:8])[:800])
    return lines


def build_review_context(
    idea: Any, build_root: str | None = None, max_chars: int = DEFAULT_MAX_CHARS
) -> str:
    """Return a compact review brief for BUILD_REVIEW, or '' if nothing built."""
    build = _current("BUILD_CODE", idea.id)
    if build is None or not isinstance(build.result_data, dict):
        return ""
    sections = []

    design = _current("DESIGN_DOC", idea.id)
    if design is not None:
        contract = render_design_contract(design.result_data)
        if contract:
            sections.append("### Design contract\n" + contract[:3000])

    manifest = _manifest_lines(build.result_data)
    if manifest:
        sections.append("### Written build\n" + "\n".join(manifest))

    release_lines = _release_lines(idea)
    if release_lines:
        heading = "### Release context"
        if getattr(idea, "release_id", None):
            release = db.session.get(Release, idea.release_id)
            if release is not None:
                heading += f" — {release.name}"
        sections.append(heading + "\n" + "\n".join(release_lines))

    if build_root:
        snapshot = existing_repo_snapshot(str(build_root))
        if snapshot:
            sections.append("### Existing project files\n" + snapshot[:SNAPSHOT_CHARS])

    text = "\n\n".join(sections)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 40)] + "\n\n[...review context truncated...]"
