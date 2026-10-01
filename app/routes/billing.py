import structlog
from flask import Blueprint, current_app, request

from app.extensions import db
from app.models import mark_stripe_event_seen
from app.services import billing as billing_svc
from app.utils.decorators import token_required
from app.utils.responses import api_error, api_ok

logger = structlog.get_logger()

bp = Blueprint("billing", __name__)


def _event_meta(payload: dict) -> tuple:
    obj = (payload.get("data") or {}).get("object") or {}
    meta = obj.get("metadata") or {}
    return payload.get("id"), payload.get("type"), obj, meta


@bp.route("/billing/webhook", methods=["POST"])
def stripe_webhook():
    """Stripe event ingress. Signature is the auth; event IDs dedupe."""
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "")
    raw = request.get_data()
    try:
        billing_svc.verify_signature(
            raw, request.headers.get("Stripe-Signature"), secret
        )
    except billing_svc.StripeWebhookError as exc:
        return api_error(str(exc), status_code=400)
    try:
        import json as _json

        payload = _json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (ValueError, TypeError, AttributeError):
        return api_error("Invalid JSON payload.", status_code=400)

    event_id, event_type, obj, meta = _event_meta(payload)
    if not event_id:
        return api_error("Missing event id.", status_code=400)
    if not mark_stripe_event_seen(event_id, event_type):
        logger.info("billing_webhook_replay", event_id=event_id, event_type=event_type)
        return api_ok({"received": True, "duplicate": True})

    instance_ref = meta.get("instance_id")
    try:
        if event_type == "checkout.session.completed":
            keys = billing_svc.apply_checkout_completed(instance_ref, meta)
            return api_ok({"received": True, "granted": keys})
        if event_type in (
            "customer.subscription.deleted",
            "customer.subscription.canceled",
        ):
            billing_svc.apply_subscription_deleted(instance_ref)
            return api_ok({"received": True, "revoked_to_free": True})
        if event_type == "invoice.payment_failed":
            logger.warning(
                "billing_payment_failed",
                instance_id=str(instance_ref),
                customer=obj.get("customer"),
            )
            # Deliberately no auto-suspend: a human decides (alerts fire
            # off this log line).
            return api_ok({"received": True, "action": "alerted"})
    except billing_svc.StripeWebhookError as exc:
        db.session.rollback()
        return api_error(str(exc), status_code=400)
    logger.info("billing_webhook_ignored", event_id=event_id, event_type=event_type)
    return api_ok({"received": True, "ignored": event_type})


@bp.route("/billing/portal", methods=["POST"])
@token_required
def billing_portal(user):
    """Customer portal link (needs STRIPE_SECRET_KEY, else 501)."""
    import httpx

    secret = current_app.config.get("STRIPE_SECRET_KEY", "")
    if not secret:
        return api_error("Billing portal is not configured.", status_code=501)
    data = request.get_json(silent=True) or {}
    customer = (data.get("customer") or "").strip()
    if not customer:
        return api_error("customer is required.", status_code=400)
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                "https://api.stripe.com/v1/billing_portal/sessions",
                data={"customer": customer},
                auth=(secret, ""),
            )
            response.raise_for_status()
            url = response.json().get("url")
    except Exception as exc:
        return api_error(f"Portal creation failed: {exc}", status_code=502)
    if not url:
        return api_error("Portal creation failed.", status_code=502)
    return api_ok({"url": url})
