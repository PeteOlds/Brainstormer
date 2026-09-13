import pytest
import uuid
from datetime import datetime, timezone, timedelta

from app.models import User, UserRole, PromptConfig, Idea, IdeaStatus, Vote, SecondaryActionResult, ActionType, IdeaStatusHistory


class TestUserModel:
    def test_create_user(self, app):
        with app.app_context():
            from app.extensions import db
            user = User(email="test@example.com", name="Test User", role=UserRole.USER)
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()
            
            assert user.email == "test@example.com"
            assert user.name == "Test User"
            assert user.role == UserRole.USER
            assert user.is_active is True
            assert user.check_password("password123")
            assert not user.check_password("wrongpassword")

    def test_user_to_dict(self, app):
        with app.app_context():
            from app.extensions import db
            user = User(email="test@example.com", name="Test User")
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()
            
            data = user.to_dict()
            assert data["email"] == "test@example.com"
            assert data["name"] == "Test User"
            assert data["role"] == "USER"
            assert "id" in data
            assert "created_at" in data

    def test_duplicate_email_raises(self, app):
        with app.app_context():
            from app.extensions import db
            user1 = User(email="test@example.com")
            user1.set_password("password123")
            db.session.add(user1)
            db.session.commit()
            
            user2 = User(email="test@example.com")
            user2.set_password("password456")
            db.session.add(user2)
            
            with pytest.raises(Exception):
                db.session.commit()


class TestPromptConfigModel:
    def test_create_prompt_config(self, app):
        with app.app_context():
            from app.models import User
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test Prompt",
                prompt_body="Generate a business idea about {{topic}}",
                interval_minutes=1440,
                model_name="llama3:8b",
                temperature=0.7,
                is_active=True,
                created_by_id=admin.id,
            )
            
            assert prompt.title == "Test Prompt"
            assert prompt.interval_minutes == 1440
            assert prompt.model_name == "llama3:8b"
            assert prompt.temperature == 0.7
            assert prompt.is_active is True
            assert prompt.prompt_body == "Generate a business idea about {{topic}}"

    def test_prompt_body_encryption(self, app):
        with app.app_context():
            from app.models import User
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            original = "Secret prompt body"
            prompt = PromptConfig(
                title="Test",
                prompt_body=original,
                interval_minutes=60,
                model_name="llama3:8b",
                created_by_id=admin.id,
            )
            
            # The stored value should be encrypted
            assert prompt._prompt_body != original
            # But accessing the property should decrypt
            assert prompt.prompt_body == original

    def test_prompt_to_dict(self, app):
        with app.app_context():
            from app.models import User
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test Prompt",
                prompt_body="Test body",
                interval_minutes=1440,
                model_name="llama3:8b",
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
            
            data = prompt.to_dict(include_prompt=True)
            assert data["title"] == "Test Prompt"
            assert data["prompt_body"] == "Test body"
            assert data["interval_minutes"] == 1440
            assert data["model_name"] == "llama3:8b"
            assert data["is_active"] is True


class TestIdeaModel:
    def test_create_idea(self, app):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test Prompt",
                prompt_body="Test body",
                interval_minutes=1440,
                model_name="llama3:8b",
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test Prompt",
                raw_content="Test idea content",
                structured_content={"elevator_pitch": "Test"},
                status=IdeaStatus.NEW,
                prompt_config_id=prompt.id,
            )
            db.session.add(idea)
            db.session.commit()
            
            assert idea.reference_code == "IDEA-0001"
            assert idea.status == IdeaStatus.NEW
            assert idea.upvotes_count == 0
            assert idea.downvotes_count == 0
            assert idea.net_score == 0

    def test_idea_to_dict(self, app):
        with app.app_context():
            from app.models import PromptConfig, User
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test Prompt",
                prompt_body="Test body",
                interval_minutes=1440,
                model_name="llama3:8b",
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
            
            idea = Idea(
                reference_code="IDEA-0001",
                prompt_title="Test Prompt",
                raw_content="Test content",
                status=IdeaStatus.NEW,
                prompt_config_id=prompt.id,
            )
            
            data = idea.to_dict(user_vote=1)
            assert data["reference_code"] == "IDEA-0001"
            assert data["status"] == "NEW"
            assert data["user_vote"] == 1
            assert "summary" in data

    def test_update_vote_counts(self, app):
        with app.app_context():
            from app.models import PromptConfig, User, Vote
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            user1 = User(email="user1@test.com")
            user1.set_password("pass123")
            user2 = User(email="user2@test.com")
            user2.set_password("pass123")
            db.session.add_all([user1, user2])
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            idea = Idea(
                reference_code="IDEA-0001", prompt_title="Test",
                raw_content="Test", prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            
            vote1 = Vote(user_id=user1.id, idea_id=idea.id, value=1)
            vote2 = Vote(user_id=user2.id, idea_id=idea.id, value=-1)
            db.session.add_all([vote1, vote2])
            db.session.commit()
            
            idea.update_vote_counts()
            assert idea.upvotes_count == 1
            assert idea.downvotes_count == 1
            assert idea.net_score == 0


class TestVoteModel:
    def test_vote_unique_constraint(self, app):
        with app.app_context():
            from app.models import Idea, PromptConfig, User, Vote
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            user = User(email="user@test.com")
            user.set_password("pass123")
            db.session.add(user)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            idea = Idea(
                reference_code="IDEA-0001", prompt_title="Test",
                raw_content="Test", prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            
            vote1 = Vote(user_id=user.id, idea_id=idea.id, value=1)
            db.session.add(vote1)
            db.session.commit()
            
            # Second vote should fail
            vote2 = Vote(user_id=user.id, idea_id=idea.id, value=-1)
            db.session.add(vote2)
            
            with pytest.raises(Exception):
                db.session.commit()


class TestSecondaryActionResultModel:
    def test_create_action_result(self, app):
        with app.app_context():
            from app.models import Idea, PromptConfig, User
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            idea = Idea(
                reference_code="IDEA-0001", prompt_title="Test",
                raw_content="Test", prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            
            action = SecondaryActionResult(
                idea_id=idea.id,
                action_type=ActionType.REFINE,
                model_used="llama3:8b",
                result_data={"elevator_pitch": "Test pitch"},
            )
            
            assert action.action_type == ActionType.REFINE
            assert action.model_used == "llama3:8b"
            assert action.result_data == {"elevator_pitch": "Test pitch"}


class TestIdeaStatusHistoryModel:
    def test_create_status_history(self, app):
        with app.app_context():
            from app.models import Idea, PromptConfig, User, IdeaStatusHistory
            from app.extensions import db
            
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            prompt = PromptConfig(
                title="Test", prompt_body="Test", interval_minutes=60,
                model_name="llama3:8b", created_by_id=admin.id
            )
            db.session.add(prompt)
            db.session.commit()
            
            idea = Idea(
                reference_code="IDEA-0001", prompt_title="Test",
                raw_content="Test", prompt_config_id=prompt.id
            )
            db.session.add(idea)
            db.session.commit()
            
            history = IdeaStatusHistory(
                idea_id=idea.id,
                changed_by_id=admin.id,
                old_status=IdeaStatus.NEW,
                new_status=IdeaStatus.CONSIDERATION,
            )
            
            assert history.old_status == IdeaStatus.NEW
            assert history.new_status == IdeaStatus.CONSIDERATION
            assert history.changed_by_id == admin.id