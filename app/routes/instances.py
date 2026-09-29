from flask import Blueprint, request

from app.extensions import db
from app.models import Instance, Membership
from app.utils.decorators import site_admin_required, token_required
from app.utils.responses import api_error, api_ok
from app.utils.tenancy import current_instance_id, is_site_admin

bp = Blueprint("instances", __name__)


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
