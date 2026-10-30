"""SSRF regression: tenant-supplied AI endpoints must be validated."""

import pytest

from app.extensions import db
from app.models import Instance, Membership, User, UserRole


@pytest.fixture()
def tenant_admin(app, client):
    from app.utils.auth import create_tokens

    with app.app_context():
        inst = Instance.query.filter_by(number=905).first()
        if inst is None:
            inst = Instance(number=905, name="SSRF Tenant")
            db.session.add(inst)
            db.session.flush()
        user = User.query.filter_by(email="ssrf-admin@test.com").first()
        if user is None:
            user = User(email="ssrf-admin@test.com", role=UserRole.USER)
            user.set_password("password123")
            db.session.add(user)
            db.session.flush()
        if (
            Membership.query.filter_by(
                user_id=user.id, instance_id=inst.id
            ).first()
            is None
        ):
            db.session.add(
                Membership(
                    user_id=user.id, instance_id=inst.id, role="INSTANCE_ADMIN"
                )
            )
        db.session.commit()
        instance_id = str(inst.id)
        tokens = create_tokens(str(user.id), user.role.value, user.email, False, instance_id)

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return client, headers, instance_id


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1:6379/",
        "http://10.0.0.1/v1",
        "file:///etc/passwd",
    ],
)
def test_ai_config_rejects_private_endpoints(tenant_admin, endpoint):
    client, headers, instance_id = tenant_admin
    res = client.put(
        f"/api/v1/instances/{instance_id}/ai-configs",
        json={"provider": "openai", "endpoint": endpoint},
        headers=headers,
    )
    assert res.status_code == 400, res.get_json()
    assert "endpoint" in res.get_json().get("message", "").lower()


def test_ai_config_accepts_a_public_endpoint(tenant_admin):
    client, headers, instance_id = tenant_admin
    res = client.put(
        f"/api/v1/instances/{instance_id}/ai-configs",
        json={"provider": "openai", "endpoint": "https://api.openai.com/v1"},
        headers=headers,
    )
    assert res.status_code == 200, res.get_json()
