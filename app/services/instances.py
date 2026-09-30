"""Instance lifecycle: create, copy-on-create, Site 5 seeding (Phase 1)."""

import uuid
from typing import Any

from app.extensions import db
from app.models import (
    ROLE_INSTANCE_ADMIN,
    ROLE_USER,
    Comment,
    Idea,
    IdeaEdit,
    IdeaStatusHistory,
    Instance,
    Membership,
    PromptConfig,
    PromptRun,
    SecondaryActionResult,
    SlackPost,
    SystemSettings,
    User,
    Vote,
)
from app.models.instance import RESERVED_INSTANCE_NUMBERS

TEMPLATE_NUMBER = 1
PRODUCTION_NUMBER = 5


class InstanceError(ValueError):
    pass


def create_instance(number: int, name: str, **attrs: Any) -> Instance:
    """Create an instance, copying config from Instance 1 (never keys)."""
    if number in RESERVED_INSTANCE_NUMBERS:
        raise InstanceError(f"Instance number {number} is reserved for future testing.")
    if Instance.query.filter_by(number=number).first():
        raise InstanceError(f"Instance number {number} already exists.")
    instance = Instance(number=number, name=name, **attrs)
    db.session.add(instance)
    db.session.flush()
    copy_template_config(instance)
    db.session.commit()
    return instance


def copy_template_config(instance: Instance) -> dict:
    """Copy prompts + settings from Instance 1. Excludes everything else.

    AI keys are never copied: instances start with whatever key columns
    exist empty (Phase 3 adds per-instance provider keys).
    """
    template = Instance.query.filter_by(number=TEMPLATE_NUMBER).first()
    if template is None:
        return {"prompts": 0, "settings": False}
    prompts = 0
    for src in PromptConfig.query.filter_by(instance_id=template.id).all():
        db.session.add(
            PromptConfig(
                instance_id=instance.id,
                title=src.title,
                _prompt_body=src._prompt_body,
                interval_minutes=src.interval_minutes,
                cron_expression=src.cron_expression,
                model_name=src.model_name,
                temperature=src.temperature,
                top_p=src.top_p,
                repeat_penalty=src.repeat_penalty,
                num_predict=src.num_predict,
                seed=src.seed,
                keep_alive=src.keep_alive,
                slack_channel=None,
                is_active=src.is_active,
                created_by_id=src.created_by_id,
            )
        )
        prompts += 1
    # Encrypted bodies copy as ciphertext; Slack channels do not carry over.
    settings_done = False
    src_settings = SystemSettings.query.filter_by(instance_id=template.id).first()
    if (
        src_settings is not None
        and SystemSettings.query.filter_by(instance_id=instance.id).first() is None
    ):
        db.session.add(
            SystemSettings(
                instance_id=instance.id,
                platform=dict(src_settings.platform or {}),
                location=dict(src_settings.location or {}),
                ai_connections=dict(src_settings.ai_connections or {}),
            )
        )
        settings_done = True
    db.session.flush()
    return {"prompts": prompts, "settings": settings_done}


# Tables whose rows move to Site 5 on first init (ideas, votes, comments
# and history — never users, which are global).
BACKFILL_TABLES: list[Any] = [
    PromptConfig,
    PromptRun,
    Idea,
    Vote,
    Comment,
    IdeaEdit,
    SecondaryActionResult,
    IdeaStatusHistory,
    SlackPost,
    SystemSettings,
]


def init_site_data() -> dict:
    """Idempotent first-time tenancy seed: Instances 1 + 5, backfill, memberships.

    All existing rows (NULL instance_id) move to Site 5. Existing users
    gain a Site 5 membership from their V1 role (ADMIN -> INSTANCE_ADMIN).
    The Site Admin itself is created separately (`promote-site-admin`).
    """
    template = Instance.query.filter_by(number=TEMPLATE_NUMBER).first()
    if template is None:
        template = Instance(number=TEMPLATE_NUMBER, name="Template")
        db.session.add(template)
        db.session.flush()
    production = Instance.query.filter_by(number=PRODUCTION_NUMBER).first()
    if production is None:
        production = Instance(number=PRODUCTION_NUMBER, name="Production")
        db.session.add(production)
        db.session.flush()

    backfilled = {}
    for model in BACKFILL_TABLES:
        count = model.query.filter(model.instance_id.is_(None)).update(
            {"instance_id": production.id}, synchronize_session=False
        )
        backfilled[model.__tablename__] = count

    memberships = 0
    for user in User.query.all():
        exists = Membership.query.filter_by(
            user_id=user.id, instance_id=production.id
        ).first()
        if exists is None:
            role = ROLE_INSTANCE_ADMIN if user.role.value == "ADMIN" else ROLE_USER
            db.session.add(
                Membership(user_id=user.id, instance_id=production.id, role=role)
            )
            memberships += 1
    db.session.commit()
    return {
        "template_id": str(template.id),
        "production_id": str(production.id),
        "backfilled": backfilled,
        "memberships": memberships,
    }


def grant_site_admin(user_id: uuid.UUID) -> Membership:
    """Grant (or return) the site-wide SITE_ADMIN membership."""
    from app.models import ROLE_SITE_ADMIN

    existing = Membership.query.filter_by(user_id=user_id, instance_id=None).first()
    if existing is not None:
        if not isinstance(existing, Membership):
            raise InstanceError("Corrupt site-admin grant.")
        return existing
    grant = Membership(user_id=user_id, instance_id=None, role=ROLE_SITE_ADMIN)
    db.session.add(grant)
    db.session.commit()
    return grant
