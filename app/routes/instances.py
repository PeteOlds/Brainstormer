from flask import Blueprint, request

from app.extensions import db
from app.models import Instance, Membership
from app.utils.decorators import site_admin_required, token_required
from app.utils.responses import api_error, api_ok
from app.utils.tenancy import current_instance_id, is_site_admin

bp = Blueprint("instances", __name__)


def _instance_admin(user, instance_id):
    """Instance admins (or site admins) for one instance, else None."""
    if is_site_admin(user):
        return "SITE_ADMIN"
    return Membership.get_role(user.id, instance_id)


def _require_instance_admin(user, instance_id):
    instance = Instance.query.get(instance_id)
    if instance is None:
        return None, api_error("Not found.", 404)
    role = _instance_admin(user, instance.id)
    if role not in ("INSTANCE_ADMIN", "SITE_ADMIN"):
        if role is None:
            return None, api_error("Not found.", 404)
        return None, api_error("Instance admin access required.", 403)
    return instance, None


@bp.route("/instances", methods=["GET"])
@token_required
def list_instances(user):
    """Own instances (memberships); site admins see everything."""
    if is_site_admin(user):
        instances = Instance.query.order_by(Instance.number.asc()).all()
    else:
        memberships = Membership.query.filter_by(user_id=user.id).all()
        ids = [m.instance_id for m in memberships if m.instance_id is not None]
        instances = (
            Instance.query.filter(Instance.id.in_(ids))
            .order_by(Instance.number.asc())
            .all()
            if ids
            else []
        )
    return api_ok({"instances": [i.to_dict() for i in instances]})


@bp.route("/instances", methods=["POST"])
@site_admin_required
def create_instance_route(user):
    """Create an instance (number, name); config copies from Instance 1."""
    from app.services import instances as instance_svc

    data = request.get_json(silent=True) or {}
    raw_number = data.get("number")
    if raw_number is None or isinstance(raw_number, bool):
        return api_error("number is required and must be an integer.", 400)
    try:
        number = int(raw_number)
    except (TypeError, ValueError):
        return api_error("number is required and must be an integer.", 400)
    name = (data.get("name") or "").strip()
    if not name:
        return api_error("name is required.", 400)
    if len(name) > 200:
        return api_error("name must be 200 characters or fewer.", 400)

    try:
        instance = instance_svc.create_instance(number, name)
    except instance_svc.InstanceError as exc:
        return api_error(str(exc), 409)
    return api_ok({"instance": instance.to_dict()}, "Instance created.", 201)


@bp.route("/instances/<uuid:instance_id>", methods=["GET"])
@token_required
def get_instance(user, instance_id):
    """One instance: members of it, or site admins. Else 404 (no leaking)."""
    instance = Instance.query.get(instance_id)
    if instance is None:
        return api_error("Not found.", 404)
    if not is_site_admin(user):
        role = Membership.get_role(user.id, instance.id)
        if role is None:
            return api_error("Not found.", 404)
        if current_instance_id() is not None and current_instance_id() != instance.id:
            return api_error("Not found.", 404)
    return api_ok({"instance": instance.to_dict()})


@bp.route("/instances/<uuid:instance_id>/ai-configs", methods=["GET"])
@token_required
def list_ai_configs(user, instance_id):
    """Provider configs for one instance (keys never leave the server)."""
    from app.models import InstanceAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    configs = InstanceAIConfig.query.filter_by(instance_id=instance.id).all()
    return api_ok({"configs": [c.to_dict() for c in configs]})


@bp.route("/instances/<uuid:instance_id>/ai-configs", methods=["PUT"])
@token_required
def upsert_ai_config(user, instance_id):
    """Create or update one provider config. `key` is write-only."""
    from app.models import CUTOFF_BEHAVIOURS, PROVIDERS, InstanceAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip().lower()
    if provider not in PROVIDERS:
        return api_error(
            f"provider is required and must be one of {', '.join(PROVIDERS)}.",
            status_code=400,
        )
    config = InstanceAIConfig.query.filter_by(
        instance_id=instance.id, provider=provider
    ).first()
    if config is None:
        config = InstanceAIConfig(instance_id=instance.id, provider=provider)
        db.session.add(config)

    if "key" in data:
        key = data["key"]
        if key is not None and not isinstance(key, str):
            return api_error("key must be a string or null.", status_code=400)
        if key:
            config.api_key = key
        elif key is None:
            config._api_key = None
    if "endpoint" in data:
        endpoint = data["endpoint"]
        if endpoint is not None and (
            not isinstance(endpoint, str) or len(endpoint) > 255
        ):
            return api_error(
                "endpoint must be a string up to 255 chars or null.", status_code=400
            )
        config.endpoint = endpoint or None
    if "model_allowlist" in data:
        allowlist = data["model_allowlist"]
        if not isinstance(allowlist, list) or any(
            not isinstance(m, str) for m in allowlist
        ):
            return api_error(
                "model_allowlist must be a list of strings.", status_code=400
            )
        config.model_allowlist = list(allowlist)
    if "embedding_model" in data:
        embedding_model = data["embedding_model"]
        if embedding_model is not None and not isinstance(embedding_model, str):
            return api_error(
                "embedding_model must be a string or null.", status_code=400
            )
        config.embedding_model = embedding_model or None
    if "budget_cents" in data:
        budget = data["budget_cents"]
        if budget is not None and (
            isinstance(budget, bool) or not isinstance(budget, int) or budget < 0
        ):
            return api_error(
                "budget_cents must be a non-negative integer or null.", status_code=400
            )
        config.budget_cents = budget
    if "cutoff_behaviour" in data:
        if data["cutoff_behaviour"] not in CUTOFF_BEHAVIOURS:
            return api_error(
                f"cutoff_behaviour must be one of {', '.join(CUTOFF_BEHAVIOURS)} (Phase 3).",
                status_code=400,
            )
        config.cutoff_behaviour = data["cutoff_behaviour"]
    if "chat_enabled" in data:
        if not isinstance(data["chat_enabled"], bool):
            return api_error("chat_enabled must be a boolean.", status_code=400)
        config.chat_enabled = data["chat_enabled"]
    db.session.commit()
    return api_ok({"config": config.to_dict()})


@bp.route("/instances/<uuid:instance_id>/spend", methods=["GET"])
@token_required
def instance_spend(user, instance_id):
    """Spend totals (rolling 30d) + budget status per configured provider."""
    from sqlalchemy import func

    from app.models import AISpendLedger, InstanceAIConfig
    from app.services.llm_backends import SPEND_WINDOW_DAYS, instance_spend_cents

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = (
        db.session.query(
            AISpendLedger.provider,
            func.coalesce(func.sum(AISpendLedger.prompt_tokens), 0),
            func.coalesce(func.sum(AISpendLedger.completion_tokens), 0),
            func.coalesce(func.sum(AISpendLedger.cost_cents), 0),
        )
        .filter(AISpendLedger.instance_id == instance.id)
        .group_by(AISpendLedger.provider)
        .all()
    )
    by_provider = {
        provider: {
            "prompt_tokens": int(pt or 0),
            "completion_tokens": int(ct or 0),
            "cost_cents": int(cost or 0),
        }
        for provider, pt, ct, cost in rows
    }
    budgets = {}
    for config in InstanceAIConfig.query.filter_by(instance_id=instance.id).all():
        spent = instance_spend_cents(instance.id) if config.budget_cents else None
        budgets[config.provider] = {
            "budget_cents": config.budget_cents,
            "spent_cents": spent,
            "exhausted": spent is not None and spent >= config.budget_cents,
        }
    return api_ok(
        {
            "instance_id": str(instance.id),
            "window_days": SPEND_WINDOW_DAYS,
            "by_provider": by_provider,
            "budgets": budgets,
        }
    )
