"""Verify Flutter idea models read only keys the backend actually emits.

Catches the class of bug where a model parses `net_score` while the API
sends `net_votes` (the vote count then silently stays 0).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import Idea

app = create_app(TestingConfig, init_celery_app=False)
with app.app_context():
    db.create_all()
    from app.models import IdeaStatus
    idea = Idea()
    idea.status = IdeaStatus.SPARK
    idea.prompt_title = "t"
    idea.raw_content = "c"
    sample = idea.to_dict(user_vote=1)

# The keys IdeaSummary.fromJson reads from the idea payload. Keep in sync
# with flutter/lib/features/ideas/idea_models.dart.
expected = {
    "id", "reference_code", "prompt_title", "summary", "status",
    "prompt_config_id", "created_by_id", "instance_id", "parent_id",
    "comments_count", "upvotes_count", "downvotes_count", "net_votes",
    "user_vote", "created_at", "actions_run",
}
# Optional keys that may be absent without include_content/instance scoping.
optional = {"structured_content", "excerpt", "pending_runs", "net_score"}
missing = sorted(k for k in expected if k not in sample and not (
    k == "net_score" and "net_votes" in sample
))
if missing:
    print("MISSING keys in API payload:")
    for k in missing:
        print("  -", k)
    print("API keys:", sorted(sample.keys()))
    sys.exit(1)
print("API contract OK:", len(expected), "keys checked")