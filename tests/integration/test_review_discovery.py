"""Review Build is a build artifact, not a global secondary action."""

from flask import g

from app.extensions import db
from app.models import SecondaryActionResult, User
from app.services.discovery import discover_actions
from tests.integration.test_build import make_instance, seed_idea


def test_review_hidden_until_a_build_is_written(app):
    with app.app_context():
        inst = make_instance(140, "RV")
        idea = seed_idea(db, inst.id, email="review-disc@t.test", status="SHIP")
        user = User.query.filter_by(email="review-disc@t.test").one()
        g.instance_role = "INSTANCE_ADMIN"
        keys = [a["key"] for a in discover_actions(user, idea)]
        assert "BUILD_REVIEW" not in keys

        db.session.add(
            SecondaryActionResult(
                idea_id=idea.id,
                action_type="BUILD_CODE",
                model_used="llama3:8b",
                provider_used="ollama",
                result_data={"written": True, "files": []},
                is_current=True,
                version=1,
                instance_id=inst.id,
            )
        )
        db.session.commit()
        keys = [a["key"] for a in discover_actions(user, idea)]
        assert "BUILD_REVIEW" in keys
