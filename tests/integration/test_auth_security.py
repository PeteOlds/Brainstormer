"""Authentication and authorisation regressions.

Each test reproduces a concrete bypass or abuse path.
"""

import pytest

from app.extensions import db
from app.models import User


def _register(client, email="user@example.com", password="password123"):
    res = client.post("/api/v1/register", json={"email": email, "password": password})
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def test_user_cannot_grant_themselves_idea_creation(app, client):
    """`can_create_ideas` is an admin control; the settings endpoint is not."""
    data, headers = _register(client, "self-grant@example.com")

    with app.app_context():
        user = User.query.filter_by(email="self-grant@example.com").one()
        user.can_create_ideas = False
        db.session.commit()

    res = client.patch(
        "/api/v1/me/settings",
        json={"can_create_ideas": True},
        headers=headers,
    )
    assert res.status_code in (400, 403), res.get_json()

    with app.app_context():
        user = User.query.filter_by(email="self-grant@example.com").one()
        assert user.can_create_ideas is False


def test_admin_can_grant_idea_creation(app, client, admin_client):
    """The admin path still works, so the feature is not simply deleted."""
    _data, _headers = _register(client, "granted@example.com")
    with app.app_context():
        user = User.query.filter_by(email="granted@example.com").one()
        user.can_create_ideas = False
        db.session.commit()
        user_id = str(user.id)

    res = admin_client.patch(
        f"/admin/users/{user_id}", json={"can_create_ideas": True}
    )
    assert res.status_code == 200, res.get_json()

    with app.app_context():
        assert (
            User.query.filter_by(email="granted@example.com").one().can_create_ideas
            is True
        )


def test_logout_revokes_the_refresh_token(client, app):
    """A stolen refresh token must stop working once the user logs out."""
    data, headers = _register(client, "logout@example.com")

    res = client.post(
        "/api/v1/logout",
        json={"refresh_token": data["refresh_token"]},
        headers=headers,
    )
    assert res.status_code == 200

    res = client.post(
        "/api/v1/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert res.status_code == 401, res.get_json()


def test_login_is_rate_limited():
    """Credential stuffing must hit a wall, not run at full speed."""
    from app import create_app
    from app.config import TestingConfig

    class RateLimitedConfig(TestingConfig):
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URI = "memory://"

    limited_app = create_app(RateLimitedConfig, init_celery_app=False)
    with limited_app.app_context():
        db.create_all()
    test_client = limited_app.test_client()

    codes = [
        test_client.post(
            "/api/v1/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        ).status_code
        for _ in range(10)
    ]
    assert 429 in codes, codes
