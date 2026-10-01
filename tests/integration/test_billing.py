"""Phase 12: Stripe webhook verification, idempotency, plan mapping."""

import hashlib
import hmac
import json
import time

from app.extensions import db
from app.models import Instance, InstanceEntitlement, User, UserRole

SECRET = "whsec-test-secret"


def sign(payload: bytes, secret=SECRET, timestamp=None):
    timestamp = timestamp or int(time.time())
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def post_event(client, event, secret=SECRET, key=None):
    raw = json.dumps(event).encode()
    headers = {"Stripe-Signature": sign(raw, secret)}
    if key:
        headers["Idempotency-Key"] = key
    return client.post(
        "/api/v1/billing/webhook",
        data=raw,
        content_type="application/json",
        headers=headers,
    )


def make_instance(number=120, free=True):
    inst = Instance(number=number, name=f"Bill {number}", is_free=free)
    db.session.add(inst)
    db.session.commit()
    return str(inst.id)


def checkout_event(iid, entitlements="hosted_ai,chat", event_id="evt_1"):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_1",
                "metadata": {"instance_id": iid, "entitlements": entitlements},
            }
        },
    }


def test_checkout_grants_and_replay_is_safe(app, client):
    app.config["STRIPE_WEBHOOK_SECRET"] = SECRET
    with app.app_context():
        iid = make_instance()

    res = post_event(client, checkout_event(iid))
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["granted"] == ["chat", "hosted_ai"]
    with app.app_context():
        from app.models import Instance as InstanceModel

        inst = InstanceModel.query.get(iid)
        assert inst.is_free is False
        rows = InstanceEntitlement.query.filter_by(instance_id=iid).all()
        assert {r.key for r in rows if r.granted} == {"hosted_ai", "chat"}

    # Stripe retries the same event: duplicate, no double-apply.
    res = post_event(client, checkout_event(iid))
    assert res.status_code == 200
    assert res.get_json()["data"].get("duplicate") is True
    with app.app_context():
        assert InstanceEntitlement.query.filter_by(instance_id=iid).count() == 2


def test_signature_and_payload_guards(app, client):
    app.config["STRIPE_WEBHOOK_SECRET"] = SECRET
    with app.app_context():
        iid = make_instance(121)

    res = client.post(
        "/api/v1/billing/webhook", data=b"{}", content_type="application/json"
    )
    assert res.status_code == 400
    event = checkout_event(iid, event_id="evt_bad")
    raw = json.dumps(event).encode()
    res = client.post(
        "/api/v1/billing/webhook",
        data=raw,
        content_type="application/json",
        headers={"Stripe-Signature": sign(raw, secret="wrong")},
    )
    assert res.status_code == 400
    old = f"t={int(time.time()) - 9999},v1=abc"
    res = client.post(
        "/api/v1/billing/webhook",
        data=raw,
        content_type="application/json",
        headers={"Stripe-Signature": old},
    )
    assert res.status_code == 400

    res = post_event(
        client,
        checkout_event(
            "00000000-0000-0000-0000-000000000000", event_id="evt_unknown_inst"
        ),
    )
    assert res.status_code == 400
    res = post_event(
        client, checkout_event(iid, entitlements="bogus", event_id="evt_unknown_key")
    )
    assert res.status_code == 400
    with app.app_context():
        from app.models import Instance as InstanceModel

        assert InstanceModel.query.get(iid).is_free is True


def test_subscription_deleted_returns_to_free(app, client):
    app.config["STRIPE_WEBHOOK_SECRET"] = SECRET
    with app.app_context():
        iid = make_instance(122, free=False)
        db.session.add(
            InstanceEntitlement(instance_id=iid, key="hosted_ai", granted=True)
        )
        db.session.commit()

    event = {
        "id": "evt_del",
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"instance_id": iid}}},
    }
    res = post_event(client, event)
    assert res.status_code == 200
    with app.app_context():
        from app.models import Instance as InstanceModel

        assert InstanceModel.query.get(iid).is_free is True
        row = InstanceEntitlement.query.filter_by(
            instance_id=iid, key="hosted_ai"
        ).first()
        assert row.granted is False


def test_payment_failed_alerts_without_mutation(app, client):
    app.config["STRIPE_WEBHOOK_SECRET"] = SECRET
    with app.app_context():
        iid = make_instance(123, free=False)

    event = {
        "id": "evt_fail",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_9", "metadata": {"instance_id": iid}}},
    }
    res = post_event(client, event)
    assert res.status_code == 200
    assert res.get_json()["data"]["action"] == "alerted"
    with app.app_context():
        from app.models import Instance as InstanceModel

        assert InstanceModel.query.get(iid).is_free is False


def test_portal_needs_secret_and_customer(app, client, auth_user):
    _email, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}
    app = client.application
    app.config["STRIPE_SECRET_KEY"] = ""
    res = client.post("/api/v1/billing/portal", json={}, headers=headers)
    assert res.status_code == 501
    app.config["STRIPE_SECRET_KEY"] = "sk-test"
    res = client.post("/api/v1/billing/portal", json={}, headers=headers)
    assert res.status_code == 400

    from unittest.mock import MagicMock, patch

    response = MagicMock()
    response.json.return_value = {"url": "https://billing.stripe.com/p/test"}
    browser = MagicMock()
    browser.__enter__.return_value = browser
    browser.post.return_value = response
    with patch("httpx.Client", return_value=browser):
        res = client.post(
            "/api/v1/billing/portal", json={"customer": "cus_1"}, headers=headers
        )
    assert res.status_code == 200
    assert res.get_json()["data"]["url"].startswith("https://billing.stripe.com")


def test_webhook_disabled_without_secret(app, client):
    app.config["STRIPE_WEBHOOK_SECRET"] = ""
    with app.app_context():
        iid = make_instance(124)
    res = post_event(client, checkout_event(iid, event_id="evt_nosecret"))
    assert res.status_code == 400
