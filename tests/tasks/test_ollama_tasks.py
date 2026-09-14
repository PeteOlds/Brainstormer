import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timezone, timedelta

from app.models import PromptConfig, Idea, SecondaryActionResult, User, UserRole
from app.schemas.ollama_schemas import RefineOutput, CompetitorsOutput, FeasibilityOutput


class TestGenerationOptions:
    def test_options_from_prompt_with_seed(self, celery_app):
        from types import SimpleNamespace
        from app.tasks.ollama_tasks import _generation_options

        cfg = SimpleNamespace(temperature=0.8, top_p=0.95, repeat_penalty=1.2,
                              num_predict=500, seed=42)
        assert _generation_options(cfg) == {
            "temperature": 0.8, "top_p": 0.95, "repeat_penalty": 1.2,
            "num_predict": 500, "seed": 42}

    def test_options_defaults_without_seed(self, celery_app):
        from types import SimpleNamespace
        from app.tasks.ollama_tasks import _generation_options

        cfg = SimpleNamespace(temperature=None, top_p=None, repeat_penalty=None,
                              num_predict=None, seed=None)
        opts = _generation_options(cfg)
        assert opts == {"temperature": 0.7, "top_p": 0.9,
                        "repeat_penalty": 1.1, "num_predict": 1000}
        assert "seed" not in opts


class TestPromptMemory:
    def _seed_prompt(self, db, admin_email="admin_mem@test.com"):
        from app.models import User, PromptConfig, UserRole
        admin = User(email=admin_email, role=UserRole.ADMIN)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        prompt = PromptConfig(
            title="Memory", prompt_body="Theme", interval_minutes=60,
            model_name="llama3:8b", created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        return prompt

    def test_empty_prompt_renders_none_yet(self, celery_app):
        with celery_app.app_context():
            from app.extensions import db
            from app.tasks.ollama_tasks import _prompt_memory
            prompt = self._seed_prompt(db)
            avoid, explore = _prompt_memory(prompt)
            assert avoid == "none yet"
            assert explore == "none yet"

    def test_avoid_lists_recent_explore_skips_discarded(self, celery_app):
        with celery_app.app_context():
            from app.extensions import db
            from app.models import Idea, IdeaStatus
            from app.tasks.ollama_tasks import _prompt_memory
            prompt = self._seed_prompt(db)
            db.session.add(Idea(
                reference_code="IDEA-M1", prompt_title="T",
                raw_content="c", structured_content={"elevator_pitch": "Old discarded winner"},
                status="DISCARDED", net_score=99, prompt_config_id=prompt.id))
            db.session.add(Idea(
                reference_code="IDEA-M2", prompt_title="T",
                raw_content="c", structured_content={"elevator_pitch": "Fresh contender"},
                status="NEW", net_score=3, prompt_config_id=prompt.id))
            db.session.commit()
            avoid, explore = _prompt_memory(prompt)
            assert "IDEA-M1" in avoid and "IDEA-M2" in avoid
            assert "IDEA-M2" in explore
            assert "IDEA-M1" not in explore

    def test_generate_includes_memory_sections(self, celery_app):
        import json
        from unittest.mock import MagicMock, patch
        with celery_app.app_context():
            from app.extensions import db
            from app.models import Idea
            from app.tasks.ollama_tasks import generate_idea
            prompt = self._seed_prompt(db, admin_email="admin_mem2@test.com")
            db.session.add(Idea(
                reference_code="IDEA-M3", prompt_title="T",
                raw_content="c", structured_content={"elevator_pitch": "Prior art"},
                prompt_config_id=prompt.id))
            db.session.commit()
            with patch('app.tasks.ollama_tasks.OllamaClient') as mc:
                m = MagicMock()
                m.generate_sync.return_value = {
                    "response": json.dumps({
                        "elevator_pitch": "A brand new idea pitch here",
                        "target_audience": "Curious early adopters worldwide",
                        "core_value_proposition": "Something genuinely different daily",
                        "monetization_strategy": "Simple subscription plan"}),
                    "done": True}
                mc.return_value = m
                generate_idea(str(prompt.id))
                sent = m.generate_sync.call_args.kwargs["prompt"]
            assert "### AVOID" in sent
            assert "IDEA-M3" in sent
            assert "### EXPLORE" in sent


class TestReferenceCode:
    def test_increments_from_highest_code(self, celery_app):
        """Regression: ordering by random-UUID id re-issued IDEA-0005 forever.

        Codes must increment past the highest existing numeric code, and a
        fresh code must never collide with an existing one.
        """
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, Idea, UserRole
            from app.tasks.ollama_tasks import _generate_reference_code

            admin = User(email="admin_refcode@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()

            existing = {r[0] for r in db.session.query(Idea.reference_code).all()}
            assert _generate_reference_code() not in existing

            for code in ("IDEA-9001", "IDEA-9002", "IDEA-9003", "IDEA-9004", "IDEA-9005", "IDEA-Z9"):
                db.session.add(Idea(
                    reference_code=code,
                    prompt_title="Test",
                    raw_content="content",
                    prompt_config_id=prompt.id,
                ))
            db.session.commit()

            # Highest numeric code is 9005 (non-numeric IDEA-Z9 skipped).
            for _ in range(5):
                db.session.expire_all()
                assert _generate_reference_code() == "IDEA-9006"

    def test_record_failure_after_poisoned_session(self, celery_app):
        """Regression: UniqueViolation poisoned the session, so mark_failed
        raised PendingRollbackError and the run orphaned as RUNNING."""
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, Idea, PromptRun, UserRole
            from app.tasks.ollama_tasks import _record_failure

            admin = User(email="admin_poison@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()

            db.session.add(Idea(
                reference_code="IDEA-9101",
                prompt_title="Test",
                raw_content="content",
                prompt_config_id=prompt.id,
            ))
            db.session.commit()

            run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
            run.mark_running()
            db.session.add(run)
            db.session.commit()
            run_id = run.id

            # Poison the session exactly like the duplicate-code flush did.
            from sqlalchemy.exc import IntegrityError
            db.session.add(Idea(
                reference_code="IDEA-9101",
                prompt_title="Test",
                raw_content="content",
                prompt_config_id=prompt.id,
            ))
            with pytest.raises(IntegrityError):
                db.session.flush()

            _record_failure(str(run_id), "duplicate key value violates unique constraint")

            db.session.expire_all()
            run = PromptRun.query.get(run_id)
            assert run.status.value == "FAILED"
            assert "duplicate key" in run.error


class TestGenerateIdeaTask:
    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_generate_idea_success(self, mock_client_class, celery_app):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock successful Ollama response with valid JSON
        mock_client.generate_sync.return_value = {
            "response": json.dumps({
                "elevator_pitch": "AI-powered inventory management for small retailers",
                "target_audience": "Small retail businesses",
                "core_value_proposition": "Automated stock optimization",
                "monetization_strategy": "SaaS subscription"
            }),
            "done": True
        }
        
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, Idea, UserRole
            from app.tasks.ollama_tasks import generate_idea
            
            # Create admin user
            admin = User(email="admin_success@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            # Create prompt config
            prompt = PromptConfig(
                title="Test Prompt",
                prompt_body="Generate a business idea about {{topic}}",
                interval_minutes=1440,
                model_name="llama3:8b",
                temperature=0.7,
                is_active=True,
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
            prompt_id = prompt.id
            
            # Call the task
            generate_idea(str(prompt_id))
            
            # Verify idea was created
            idea = Idea.query.filter_by(prompt_config_id=prompt.id).first()
            assert idea is not None
            assert idea.reference_code.startswith("IDEA-")
            assert idea.status == "NEW"
            assert idea.prompt_config_id == prompt.id
            
            # Verify structured content was parsed (structured_content is db.JSON type, auto-deserialized to dict)
            structured = idea.structured_content  # Already a dict from JSON column type
            assert "elevator_pitch" in structured
            assert "target_audience" in structured
            
            # Verify prompt config was updated
            # (expire first: the task runs in a nested app context with its
            # own session, so this session holds a stale cached copy.)
            db.session.expire_all()
            prompt = PromptConfig.query.get(prompt.id)
            assert prompt.last_run_at is not None
            assert prompt.next_run_at is not None

            # The admin's prompt_body must reach Ollama (was silently ignored).
            sent_prompt = mock_client.generate_sync.call_args.kwargs["prompt"]
            assert "Generate a business idea about {{topic}}" in sent_prompt
            # Generation params use documented defaults when unset.
            assert mock_client.generate_sync.call_args.kwargs["options"] == {
                "temperature": 0.7, "top_p": 0.9,
                "repeat_penalty": 1.1, "num_predict": 1000}
            assert mock_client.generate_sync.call_args.kwargs["keep_alive"] == "2h"

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_generate_idea_prompt_not_found(self, mock_client, celery_app):
        with celery_app.app_context():
            from app.tasks.ollama_tasks import generate_idea

            # Call with non-existent prompt ID
            generate_idea("00000000-0000-0000-0000-000000000000")


class TestSecondaryActionRobustness:
    def _seed(self, db, email="admin_sec@test.com", temperature=0.9):
        from app.models import User, PromptConfig, Idea, UserRole
        admin = User(email=email, role=UserRole.ADMIN)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        prompt = PromptConfig(
            title="Sec", prompt_body="Test", interval_minutes=60,
            model_name="llama3:8b", temperature=temperature,
            created_by_id=admin.id)
        db.session.add(prompt)
        db.session.commit()
        idea = Idea(
            reference_code="IDEA-S1",
            prompt_title="Test Prompt",
            raw_content="AI-powered inventory management for small retailers.",
            prompt_config_id=prompt.id)
        db.session.add(idea)
        db.session.commit()
        return idea

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_secondary_runs_cold(self, mock_client_class, celery_app):
        """Analytical actions cap temperature at 0.3 (prompt had 0.9)."""
        import json as _json
        with celery_app.app_context():
            from app.tasks.ollama_tasks import run_secondary_action
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": _json.dumps({
                    "elevator_pitch": "AI inventory management refined",
                    "target_audience": "Small retail businesses",
                    "core_value_proposition": "Automated stock optimization",
                    "monetization_strategy": "SaaS subscription"}),
                "done": True}
            from app.extensions import db
            idea = self._seed(db)
            run_secondary_action(str(idea.id), "REFINE")
            opts = mock_client.generate_sync.call_args.kwargs["options"]
            assert opts["temperature"] == 0.3

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_run_secondary_action_five_forces(self, mock_client_class, celery_app):
        import json as _json
        with celery_app.app_context():
            from app.extensions import db
            from app.models import SecondaryActionResult
            from app.tasks.ollama_tasks import run_secondary_action
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": _json.dumps({
                    "competitive_rivalry": "Fragmented rivals compete on price in a growing market overall.",
                    "threat_of_substitutes": "Manual workarounds and spreadsheets persist widely.",
                    "threat_of_new_entrants": "Low capital needs but brand loyalty protects incumbents.",
                    "bargaining_power_of_buyers": "Many small buyers, price sensitive, low switching costs.",
                    "bargaining_power_of_suppliers": "Commodity inputs keep supplier power low.",
                    "market_attractiveness": "Attractive niche with differentiation openings.",
                    "primary_risks": ["Price war"],
                    "recommendations": ["Own a narrow vertical first"]}),
                "done": True}
            idea = self._seed(db, email="admin_sec4@test.com")
            run_secondary_action(str(idea.id), "FIVE_FORCES")
            assert SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type="FIVE_FORCES").count() == 1

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_run_secondary_action_pestel(self, mock_client_class, celery_app):
        import json as _json
        with celery_app.app_context():
            from app.extensions import db
            from app.models import SecondaryActionResult
            from app.tasks.ollama_tasks import run_secondary_action
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": _json.dumps({
                    "political": "Stable policy environment with supportive startup legislation.",
                    "economic": "Moderate inflation with steady consumer spending power.",
                    "social": "Growing sustainability culture among younger demographics.",
                    "technological": "Rapid AI tooling advances lower build costs.",
                    "environmental": "Tightening packaging rules raise compliance costs.",
                    "legal": "Standard consumer protection plus privacy duties.",
                    "opportunities": ["Green subsidies"],
                    "threats": ["Recession"],
                    "recommendations": ["Launch in subsidised regions"]}),
                "done": True}
            idea = self._seed(db, email="admin_sec5@test.com")
            run_secondary_action(str(idea.id), "PESTEL")
            assert SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type="PESTEL").count() == 1

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_validation_error_strict_retry(self, mock_client_class, celery_app):
        """First bad schema output triggers one strict retry; success stored."""
        import json as _json
        with celery_app.app_context():
            from app.extensions import db
            from app.models import SecondaryActionResult
            from app.tasks.ollama_tasks import run_secondary_action
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            good = _json.dumps({
                "elevator_pitch": "AI inventory management refined",
                "target_audience": "Small retail businesses",
                "core_value_proposition": "Automated stock optimization",
                "monetization_strategy": "SaaS subscription"})
            mock_client.generate_sync.side_effect = [
                {"response": _json.dumps({"wrong": "shape"}), "done": True},
                {"response": good, "done": True}]
            idea = self._seed(db, email="admin_sec2@test.com")
            run_secondary_action(str(idea.id), "REFINE")
            assert mock_client.generate_sync.call_count == 2
            retry_prompt = mock_client.generate_sync.call_args_list[1].kwargs["prompt"]
            assert "FAILED validation" in retry_prompt
            assert SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type="REFINE").count() == 1

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_fenced_json_accepted(self, mock_client_class, celery_app):
        """Markdown fences around valid JSON no longer fail validation."""
        import json as _json
        with celery_app.app_context():
            from app.extensions import db
            from app.models import SecondaryActionResult
            from app.tasks.ollama_tasks import run_secondary_action
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            good = _json.dumps({
                "elevator_pitch": "AI inventory management refined",
                "target_audience": "Small retail businesses",
                "core_value_proposition": "Automated stock optimization",
                "monetization_strategy": "SaaS subscription"})
            mock_client.generate_sync.return_value = {
                "response": "```json\n" + good + "\n```", "done": True}
            idea = self._seed(db, email="admin_sec3@test.com")
            run_secondary_action(str(idea.id), "REFINE")
            assert mock_client.generate_sync.call_count == 1
            assert SecondaryActionResult.query.filter_by(
                idea_id=idea.id, action_type="REFINE").count() == 1


class TestRunSecondaryActionTask:
    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_run_secondary_action_refine(self, mock_client_class, celery_app):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_client.generate_sync.return_value = {
            "response": json.dumps({
                "elevator_pitch": "AI inventory management for small retailers",
                "target_audience": "Small retail businesses",
                "core_value_proposition": "Automated stock optimization",
                "monetization_strategy": "SaaS subscription"
            }),
            "done": True
        }
        
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, Idea, SecondaryActionResult, UserRole
            from app.tasks.ollama_tasks import run_secondary_action
            
            # Create admin user
            admin = User(email="admin_refine@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            # Create prompt
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            # Create idea
            idea = Idea(
                reference_code="IDEA-8101",
                prompt_title="Test Prompt",
                raw_content="AI-powered inventory management for small retailers using computer vision.",
                prompt_config_id=prompt.id,
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
            
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": json.dumps({
                    "elevator_pitch": "AI inventory management for small retailers",
                    "target_audience": "Small retail businesses",
                    "core_value_proposition": "Automated stock optimization",
                    "monetization_strategy": "SaaS subscription"
                }),
                "done": True
            }
            
            run_secondary_action(str(idea_id), "REFINE")
            
            result = SecondaryActionResult.query.filter_by(
                idea_id=idea_id, action_type="REFINE"
            ).first()
            
            assert result is not None
            assert result.action_type == "REFINE"
            assert result.model_used == "llama3:8b"
            assert "elevator_pitch" in result.result_data

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_run_secondary_action_competitors(self, mock_client_class, celery_app):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_client.generate_sync.return_value = {
            "response": json.dumps({
                "direct_competitors": [
                    {"name": "Sortly", "description": "Inventory app", "advantage_over_idea": "Established user base"}
                ],
                "indirect_competitors": ["Excel spreadsheets"],
                "differentiator": "AI-powered computer vision",
                "barriers_to_entry": ["Data acquisition", "Model accuracy"]
            }),
            "done": True
        }
        
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, Idea, SecondaryActionResult, UserRole
            from app.tasks.ollama_tasks import run_secondary_action
            
            # Create admin user
            admin = User(email="admin_comp@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            # Create prompt
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            # Create idea
            idea = Idea(
                reference_code="IDEA-8102",
                prompt_title="Test Prompt",
                raw_content="AI-powered inventory management for small retailers using computer vision.",
                prompt_config_id=prompt.id,
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
            
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": json.dumps({
                    "direct_competitors": [
                        {"name": "Sortly", "description": "Inventory app", "advantage_over_idea": "Established user base"}
                    ],
                    "indirect_competitors": ["Excel spreadsheets"],
                    "differentiator": "AI-powered computer vision",
                    "barriers_to_entry": ["Data acquisition", "Model accuracy"]
                }),
                "done": True
            }
            
            run_secondary_action(str(idea_id), "COMPETITORS")
            
            result = SecondaryActionResult.query.filter_by(
                idea_id=idea_id, action_type="COMPETITORS"
            ).first()
            
            assert result is not None
            assert result.action_type == "COMPETITORS"
            assert "direct_competitors" in result.result_data

    @patch('app.tasks.ollama_tasks.OllamaClient')
    def test_run_secondary_action_model_override(self, mock_client_class, celery_app):
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, Idea, UserRole
            from app.tasks.ollama_tasks import run_secondary_action
            
            # Create admin user
            admin = User(email="admin_override@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            # Create prompt
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            # Create idea
            idea = Idea(
                reference_code="IDEA-8103",
                prompt_title="Test Prompt",
                raw_content="AI-powered inventory management for small retailers using computer vision.",
                prompt_config_id=prompt.id,
            )
            db.session.add(idea)
            db.session.commit()
            idea_id = idea.id
            
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.generate_sync.return_value = {
                "response": json.dumps({
                    "elevator_pitch": "AI inventory management",
                    "target_audience": "Small retailers",
                    "core_value_proposition": "Automated stock optimization",
                    "monetization_strategy": "SaaS subscription"
                }),
                "done": True
            }
            
            run_secondary_action(str(idea_id), "REFINE", model_override="mistral:7b")
            
            # Verify model_override was used
            call_args = mock_client_class.return_value.generate_sync.call_args
            assert call_args.kwargs["model"] == "mistral:7b"


class TestCheckDuePromptsTask:
    @patch('app.tasks.ollama_tasks.generate_idea')
    def test_check_due_prompts(self, mock_generate_idea, celery_app):
        with celery_app.app_context():
            from app.extensions import db
            from app.models import User, PromptConfig, UserRole
            from app.tasks.ollama_tasks import check_due_prompts
            from datetime import datetime, timezone, timedelta
            
            admin = User(email="admin_due@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            # Due prompt
            due_prompt = PromptConfig(
                title="Due Prompt",
                prompt_body="Test",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=True,
                created_by_id=admin.id,
                next_run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
            
            # Not due prompt
            future_prompt = PromptConfig(
                title="Future Prompt",
                prompt_body="Test",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=True,
                created_by_id=admin.id,
                next_run_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            
            # Inactive prompt
            inactive_prompt = PromptConfig(
                title="Inactive Prompt",
                prompt_body="Test",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=False,
                created_by_id=admin.id,
                next_run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
            
            db.session.add_all([due_prompt, future_prompt, inactive_prompt])
            db.session.commit()

            # The mocked .delay() returns a MagicMock; give its .id a real
            # string so run.job_id binds on commit.
            mock_generate_idea.delay.return_value.id = "mock-job-id"

            check_due_prompts()
            
            # Should only enqueue the due active prompt
            mock_generate_idea.delay.assert_called_once()


class TestRecordFailure_format:
    def test_empty_message_exception_keeps_class_name(self, celery_app):
        """httpx ConnectTimeout str() is empty — must not become 'Unknown error'."""
        with celery_app.app_context():
            from app.extensions import db
            from app.models import PromptConfig, PromptRun, User, UserRole
            from app.tasks.ollama_tasks import _record_failure

            admin = User(email="admin_fmterr@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            prompt = PromptConfig(
                title="Fmt", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id)
            db.session.add(prompt)
            db.session.commit()
            run = PromptRun(prompt_config_id=prompt.id, triggered_by="manual")
            db.session.add(run)
            db.session.commit()
            run_id = run.id

            import httpx
            _record_failure(str(run_id), httpx.ConnectTimeout(""))

            db.session.expire_all()
            run = PromptRun.query.get(run_id)
            assert run.status.value == "FAILED"
            assert run.error == "ConnectTimeout"
