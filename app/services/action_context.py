"""Build rich context for secondary AI actions.

Collects all supporting material for an idea: comments, structured fields,
prior secondary action results, votes. Truncated to fit token budget.
"""
import json
from typing import Any

from app.extensions import db
from app.models import Comment, Idea, SecondaryActionResult, Vote
from sqlalchemy import func


def build_idea_context(idea: Idea, max_chars: int = 8000) -> str:
    """Build a rich context string for an idea, including all supporting material.

    Returns a formatted string with sections for:
    - Structured content fields
    - Comments (newest first, truncated if needed)
    - Prior secondary action results
    - Vote summary

    Total output is capped at max_chars.
    """
    sections = []

    # 1. Structured content
    sc = idea.structured_content
    if isinstance(sc, dict) and sc:
        parts = []
        for key, value in sc.items():
            if isinstance(value, str) and value.strip():
                parts.append(f"{key.replace('_', ' ').title()}: {value.strip()}")
        if parts:
            sections.append("### Structured Content\n" + "\n".join(parts))

    # 2. Comments (newest first, with authors)
    comments = (
        Comment.query.filter_by(idea_id=idea.id, is_deleted=False)
        .order_by(Comment.created_at.desc())
        .all()
    )
    if comments:
        comment_lines = []
        for c in comments:
            author = c.user.name if c.user and c.user.name else (c.user.email if c.user else "Unknown")
            body = c.body[:500] + ("..." if len(c.body) > 500 else "")
            comment_lines.append(f"- {author} ({c.created_at.strftime('%Y-%m-%d')}): {body}")
        sections.append("### Comments\n" + "\n".join(comment_lines))

    # 2b. Per-document discussion threads (PRD/Design versions)
    doc_comments = (
        Comment.query.filter_by(idea_id=idea.id, scope="doc", is_deleted=False)
        .order_by(Comment.created_at.desc())
        .all()
    )
    if doc_comments:
        by_doc = {}
        for c in doc_comments:
            by_doc.setdefault(c.action_result_id, []).append(c)
        doc_lines = []
        results = SecondaryActionResult.query.filter(
            SecondaryActionResult.id.in_(list(by_doc))).all()
        label_by_id = {r.id: f"{r.action_type.replace('_', ' ').title()} v{r.version}" for r in results}
        for rid, thread in by_doc.items():
            label = label_by_id.get(rid, "Document")
            for c in thread:
                author = c.user.name if c.user and c.user.name else (c.user.email if c.user else "Unknown")
                body = c.body[:300] + ("..." if len(c.body) > 300 else "")
                doc_lines.append(f"- [{label}] {author}: {body}")
        if doc_lines:
            sections.append("### Document Discussions\n" + "\n".join(doc_lines))

    # 3. Prior secondary action results
    actions = (
        SecondaryActionResult.query.filter_by(idea_id=idea.id)
        .order_by(SecondaryActionResult.executed_at.desc())
        .all()
    )
    if actions:
        action_lines = []
        for a in actions:
            action_name = a.action_type.replace("_", " ").title()
            # Summarize result - just show keys and a brief summary
            if isinstance(a.result_data, dict):
                keys = list(a.result_data.keys())[:5]
                action_lines.append(f"- {action_name}: {', '.join(keys)}")
            else:
                action_lines.append(f"- {action_name}: completed")
        sections.append("### Prior Analyses\n" + "\n".join(action_lines))

    # 4. Vote summary
    upvotes = db.session.query(func.count(Vote.id)).filter(
        Vote.idea_id == idea.id, Vote.value == 1
    ).scalar() or 0
    downvotes = db.session.query(func.count(Vote.id)).filter(
        Vote.idea_id == idea.id, Vote.value == -1
    ).scalar() or 0
    net = upvotes - downvotes
    vote_summary = f"Upvotes: {upvotes}, Downvotes: {downvotes}, Net: {net}"
    sections.append("### Votes\n" + vote_summary)

    # Combine and truncate
    full = "\n\n".join(sections)
    if len(full) <= max_chars:
        return full

    # Truncate from the end (preserve structured content, comments first)
    # Simple truncation with marker
    return full[:max_chars - 100] + "\n\n[...truncated due to length...]"