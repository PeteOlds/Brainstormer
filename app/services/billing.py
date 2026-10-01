"""Stripe billing webhooks (Phase 12): plans map 1:1 onto entitlement keys.

Signature verification is hand-rolled HMAC (no new dependency):
`Stripe-Signature: t=...,v1=...`, signed payload `t.body`, 5-minute
tolerance. Event IDs dedupe retries before any mutation. Metadata on
the Stripe objects drives everything (`instance_id`, comma-separated
`entitlements`); unknown instances or keys fail closed with 400.
"""

import hashlib
import hmac
import structlog
import time
from typing import Any

import structlog

logger = structlog.get_logger()

SIGNATURE_TOLERANCE_SECONDS = 300


class StripeWebhookError(ValueError):
    pass


def verify_signature(payload: bytes, header: str | None, secret: str) -> None:
    """Raise StripeWebhookError unless the Stripe signature checks out."""
    if not secret:
        raise StripeWebhookError("Webhook signing is not configured.")
    if not header:
        raise StripeWebhookError("Missing Stripe-Signature header.")
    timestamp = None
    signatures = []
    for part in header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        if key.strip() == "t":
            timestamp = value.strip()
        elif key.strip() == "v1":
            signatures.append(value.strip())
    if timestamp is None or not signatures:
        raise StripeWebhookError("Malformed Stripe-Signature header.")
    try:
        skew = abs(time.time() - int(timestamp))
    except (TypeError, ValueError) as exc:
        raise StripeWebhookError("Bad signature timestamp.") from exc
    if skew > SIGNATURE_TOLERANCE_SECONDS:
        raise StripeWebhookError("Signature timestamp outside tolerance.")
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise StripeWebhookError("Signature mismatch.")


def parse_entitlements(metadata: Any) -> list:
    """Comma-separated entitlement keys from Stripe metadata (validated)."""
    from app.models import ENTITLEMENTS

    raw = metadata.get("entitlements", "") or ""
    keys = [k.strip() for k in str(raw).split(",") if k.strip()]
    unknown = [k for k in keys if k not in ENTITLEMENTS]
    if unknown:
        raise StripeWebhookError(f"Unknown entitlement keys: {', '.join(unknown)}.")
    if "core" in keys:
        keys = [k for k in keys if k != "core"]  # baseline, never stored
    return sorted(set(keys))


def apply_checkout_completed(instance_id: Any, metadata: Any) -> list:
    """Grant purchased entitlements; flip the instance off Free."""
    import uuid as uuid_mod

    from app.extensions import db
    from app.models import Instance, InstanceEntitlement

    try:
        iid = uuid_mod.UUID(str(instance_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise StripeWebhookError("Bad instance_id metadata.") from exc
    instance = db.session.get(Instance, iid)
    if instance is None:
        raise StripeWebhookError("Unknown instance in metadata.")
    keys = parse_entitlements(metadata)
    for key in keys:
        row = InstanceEntitlement.query.filter_by(instance_id=iid, key=key).first()
        if row is None:
            row = InstanceEntitlement(instance_id=iid, key=key)
            db.session.add(row)
        row.granted = True
    instance.is_free = False
    db.session.commit()
    logger.info(
        "billing_checkout_completed",
        instance_id=str(iid),
        entitlements=keys,
    )
    return keys


def apply_subscription_deleted(instance_id: Any) -> None:
    """Return the instance to the Free baseline (revoke non-core grants)."""
    import uuid as uuid_mod

    from app.extensions import db
    from app.models import Instance, InstanceEntitlement

    try:
        iid = uuid_mod.UUID(str(instance_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise StripeWebhookError("Bad instance_id metadata.") from exc
    instance = db.session.get(Instance, iid)
    if instance is None:
        raise StripeWebhookError("Unknown instance in metadata.")
    for row in InstanceEntitlement.query.filter_by(instance_id=iid).all():
        if row.key != "core":
            row.granted = False
    instance.is_free = True
    db.session.commit()
    logger.info("billing_subscription_deleted", instance_id=str(iid))
