"""Full pipeline must continue through Design to a Build preview."""

import json
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import IdeaStatus, InstanceBuildTarget, SecondaryActionResult
from tests.integration.test_build import MANIFEST, make_instance, seed_idea, seed_target

PRD = {
    "executive_summary": "Problem X for audience Y with KPI Z clearly stated here.",
    "user_personas": "Primary persona works this way and feels that pain daily.",
    "product_scope": "MVP must-haves listed, nice-to-haves deferred to phase two.",
    "functional_requirements": "Given a user When they act Then the system responds.",
    "non_functional_requirements": "99.9% uptime, encrypted data, GDPR posture.",
    "ux_guidelines": "Three-step flow with loading, empty and error states covered.",
    "assumptions_risks": "Depends on API Q with fallback and mitigation plan.",
    "open_questions": [],
}

DESIGN = {
    "architecture": "Single Flask service with SQLite and a small web client.",
    "screens": "Home list and idea detail with clear empty states.",
    "data_model": "Idea with id, title and status fields.",
    "api_contracts": "GET /api/ideas returns a list of ideas.",
    "build_notes": "Build the list first, then the detail screen.",
    "open_questions": [],
}


def test_full_pipeline_reaches_build_preview(celery_app, tmp_path):
    celery_app.config["OPENCODE_BUILD_ROOTS"] = str(tmp_path)
    with celery_app.app_context():
        inst = make_instance(91, "FP")
        idea = seed_idea(db, inst.id, email="fp@t.test", status="SPARK")
        # no pre-registered repo: full pipeline must resolve one itself

        responses = [PRD, DESIGN, MANIFEST]
        with patch("app.tasks.ollama_tasks.OllamaClient") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            client.generate_sync.side_effect = [
                {"response": json.dumps(payload)} for payload in responses
            ]
            from app.tasks.ollama_tasks import run_full_pipeline

            run_full_pipeline.run(str(idea.id))

        types = {
            row.action_type
            for row in SecondaryActionResult.query.filter_by(idea_id=idea.id).all()
        }
        assert "PRD_DOC" in types
        assert "DESIGN_DOC" in types
        assert "BUILD_CODE" in types, "pipeline stopped before the Build preview"
        assert InstanceBuildTarget.query.filter_by(instance_id=inst.id).count() == 1
