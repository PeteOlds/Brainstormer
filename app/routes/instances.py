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


@bp.route("/instances/<uuid:instance_id>/oauth", methods=["GET"])
@token_required
def list_oauth_configs(user, instance_id):
    """Social login credentials per provider (secrets never leave)."""
    from app.models import TenantOAuthConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    configs = TenantOAuthConfig.query.filter_by(instance_id=instance.id).all()
    return api_ok({"configs": [c.to_dict() for c in configs]})


@bp.route("/instances/<uuid:instance_id>/oauth", methods=["PUT"])
@token_required
def upsert_oauth_config(user, instance_id):
    """Create or update one provider's OAuth credentials (secret write-only).

    Apple note: paste a generated client-secret JWT (Apple has no static
    secret); rotation happens at Apple, then update here.
    """
    from app.models import OAUTH_PROVIDERS, TenantOAuthConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip().lower()
    if provider not in OAUTH_PROVIDERS:
        return api_error(
            f"provider is required and must be one of {', '.join(OAUTH_PROVIDERS)}.",
            status_code=400,
        )
    client_id = (data.get("client_id") or "").strip()
    if not client_id or len(client_id) > 255:
        return api_error("client_id is required (max 255 chars).", status_code=400)
    secret = data.get("client_secret")
    if secret is not None and not isinstance(secret, str):
        return api_error("client_secret must be a string or null.", status_code=400)
    config = TenantOAuthConfig.query.filter_by(
        instance_id=instance.id, provider_name=provider
    ).first()
    if config is None:
        config = TenantOAuthConfig(instance_id=instance.id, provider_name=provider)
        db.session.add(config)
    config.client_id = client_id
    if secret:
        config.client_secret = secret
    elif secret is None:
        config._client_secret = None
    db.session.commit()
    return api_ok({"config": config.to_dict()})


def _member_entry(membership):
    from app.models import User as UserModel

    member = UserModel.query.get(membership.user_id)
    return {
        "user_id": str(membership.user_id),
        "email": member.email if member else None,
        "name": member.name if member else None,
        "role": membership.role,
    }


@bp.route("/instances/<uuid:instance_id>/members", methods=["GET"])
@token_required
def list_members(user, instance_id):
    """Membership roster for one instance."""
    from app.models import Membership as MembershipModel

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    memberships = MembershipModel.query.filter_by(instance_id=instance.id).all()
    return api_ok({"members": [_member_entry(m) for m in memberships]})


def _last_admin_guard(instance_id, target_user_id):
    from app.models import Membership as MembershipModel
    from app.models import ROLE_INSTANCE_ADMIN

    others = MembershipModel.query.filter(
        MembershipModel.instance_id == instance_id,
        MembershipModel.role == ROLE_INSTANCE_ADMIN,
        MembershipModel.user_id != target_user_id,
    ).count()
    if others == 0:
        return api_error("Cannot remove the last instance admin.", 409)
    return None


@bp.route("/instances/<uuid:instance_id>/members/<uuid:member_id>", methods=["PATCH"])
@token_required
def update_member(user, instance_id, member_id):
    """Change a member's role (INSTANCE_ADMIN/USER)."""
    from app.models import ROLE_INSTANCE_ADMIN, ROLE_USER, Membership as MembershipModel

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    if data.get("role") not in (ROLE_INSTANCE_ADMIN, ROLE_USER):
        return api_error(
            f"role must be {ROLE_INSTANCE_ADMIN} or {ROLE_USER}.", status_code=400
        )
    membership = MembershipModel.query.filter_by(
        user_id=member_id, instance_id=instance.id
    ).first()
    if membership is None:
        return api_error("Member not found.", 404)
    if str(member_id) == str(user.id) and not is_site_admin(user):
        return api_error("You cannot change your own membership.", 403)
    if membership.role == ROLE_INSTANCE_ADMIN and data["role"] == ROLE_USER:
        blocked = _last_admin_guard(instance.id, member_id)
        if blocked:
            return blocked
    membership.role = data["role"]
    db.session.commit()
    return api_ok({"member": _member_entry(membership)})


@bp.route("/instances/<uuid:instance_id>/members/<uuid:member_id>", methods=["DELETE"])
@token_required
def remove_member(user, instance_id, member_id):
    """Remove a membership (never yourself, never the last admin)."""
    from app.models import ROLE_INSTANCE_ADMIN, Membership as MembershipModel

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    membership = MembershipModel.query.filter_by(
        user_id=member_id, instance_id=instance.id
    ).first()
    if membership is None:
        return api_error("Member not found.", 404)
    if str(member_id) == str(user.id):
        return api_error("You cannot remove your own membership.", 403)
    if membership.role == ROLE_INSTANCE_ADMIN:
        blocked = _last_admin_guard(instance.id, member_id)
        if blocked:
            return blocked
    db.session.delete(membership)
    db.session.commit()
    return api_ok({"removed": str(member_id)})


@bp.route("/instances/<uuid:instance_id>/export", methods=["GET"])
@token_required
def export_instance_bundle(user, instance_id):
    """Download this instance's JSON bundle (self-service export)."""
    from flask import jsonify

    from app.services import backup as backup_svc

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    try:
        bundle = backup_svc.export_instance(instance.id)
    except backup_svc.BackupIntegrityError as exc:
        return api_error(str(exc), 404)
    response = jsonify(bundle)
    response.headers["Content-Disposition"] = (
        f"attachment; filename=instance-{instance.number}.json"
    )
    return response


@bp.route("/instances/<uuid:instance_id>/entitlements", methods=["GET"])
@token_required
def list_entitlements(user, instance_id):
    """Granted keys (resolved) plus stored overrides and billing flags."""
    from app.models import InstanceEntitlement, resolve_entitlements

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = InstanceEntitlement.query.filter_by(instance_id=instance.id).all()
    return api_ok(
        {
            "instance_id": str(instance.id),
            "is_free": instance.is_free,
            "status": instance.status,
            "granted": sorted(resolve_entitlements(instance)),
            "overrides": [r.to_dict() for r in rows],
        }
    )


@bp.route("/instances/<uuid:instance_id>/entitlements", methods=["PUT"])
@site_admin_required
def set_entitlement(user, instance_id):
    """Grant/revoke one entitlement (site admin; billing is manual)."""
    from app.models import ENTITLEMENTS, InstanceEntitlement

    instance = Instance.query.get(instance_id)
    if instance is None:
        return api_error("Not found.", 404)
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    if key not in ENTITLEMENTS:
        return api_error(
            f"key must be one of {', '.join(ENTITLEMENTS)}.", status_code=400
        )
    granted = data.get("granted", True)
    if not isinstance(granted, bool):
        return api_error("granted must be a boolean.", status_code=400)
    limits = data.get("limits", {})
    if not isinstance(limits, dict):
        return api_error("limits must be an object.", status_code=400)
    row = InstanceEntitlement.query.filter_by(instance_id=instance.id, key=key).first()
    if row is None:
        row = InstanceEntitlement(instance_id=instance.id, key=key)
        db.session.add(row)
    row.granted = granted
    row.limits = dict(limits)
    db.session.commit()
    return api_ok({"entitlement": row.to_dict()})


@bp.route("/instances/<uuid:instance_id>/stage-config", methods=["GET"])
@token_required
def list_stage_configs(user, instance_id):
    """Per-stage AI settings for one instance (stages without rows inherit)."""
    from app.models import STAGES, StageAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    rows = StageAIConfig.query.filter_by(instance_id=instance.id).all()
    by_stage = {r.stage: r.to_dict() for r in rows}
    return api_ok(
        {
            "stages": [by_stage.get(stage) for stage in STAGES],
        }
    )


@bp.route("/instances/<uuid:instance_id>/stage-config", methods=["PUT"])
@token_required
def upsert_stage_config(user, instance_id):
    """Create or update one stage's AI settings (unchecked keys inherit)."""
    from app.models import PROVIDERS, STAGES, StageAIConfig

    instance, err = _require_instance_admin(user, instance_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    stage = (data.get("stage") or "").strip().upper()
    if stage not in STAGES:
        return api_error(
            f"stage is required and must be one of {', '.join(STAGES)}.",
            status_code=400,
        )
    provider = data.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower() or None
        if provider is not None and provider not in PROVIDERS:
            return api_error(
                f"provider must be one of {', '.join(PROVIDERS)}.",
                status_code=400,
            )
    temperature = _optional_float(data.get("temperature"), "temperature", 0, 2)
    if isinstance(temperature, tuple):
        return temperature
    top_p = _optional_float(data.get("top_p"), "top_p", 0, 1)
    if isinstance(top_p, tuple):
        return top_p
    num_predict = data.get("num_predict")
    if num_predict is not None:
        try:
            num_predict = int(num_predict)
        except (TypeError, ValueError):
            return api_error("num_predict must be an integer.", status_code=400)
        if not 1 <= num_predict <= 4096:
            return api_error("num_predict must be 1-4096.", status_code=400)
    for list_key in ("skills", "guidelines"):
        if list_key in data and (
            not isinstance(data[list_key], list)
            or any(not isinstance(v, str) for v in data[list_key])
        ):
            return api_error(f"{list_key} must be a list of strings.", status_code=400)
    model_name = data.get("model_name")
    if model_name is not None:
        model_name = str(model_name).strip() or None
        if model_name is not None and len(model_name) > 100:
            return api_error(
                "model_name must be 100 characters or fewer.", status_code=400
            )
    row = StageAIConfig.query.filter_by(instance_id=instance.id, stage=stage).first()
    if row is None:
        row = StageAIConfig(instance_id=instance.id, stage=stage)
        db.session.add(row)
    if "provider" in data:
        row.provider = provider
    if "model_name" in data:
        row.model_name = model_name
    if "temperature" in data:
        row.temperature = temperature
    if "top_p" in data:
        row.top_p = top_p
    if "num_predict" in data:
        row.num_predict = num_predict
    if "skills" in data:
        row.skills = list(data["skills"])
    if "guidelines" in data:
        row.guidelines = list(data["guidelines"])
    db.session.commit()
    return api_ok({"stage_config": row.to_dict()})


def _optional_float(value, name, lo, hi):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return api_error(f"{name} must be a number.", status_code=400)
    if not lo <= number <= hi:
        return api_error(f"{name} must be between {lo} and {hi}.", status_code=400)
    return number
