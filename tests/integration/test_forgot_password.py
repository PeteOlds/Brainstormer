"""Forgotten password flow."""

import pytest

from app.extensions import db
from app.models import PasswordResetToken, User, UserRole


def _user(app, email="reset@example.com"):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        if u is None:
            u = User(email=email, role=UserRole.USER)
            u.set_password("oldpassword1")
            db.session.add(u)
            db.session.commit()
        return u


def test_forgot_password_unknown_email_returns_200(client, app):
    res = client.post("/api/v1/forgot-password", json={"email": "nobody@example.com"})
    assert res.status_code == 200


def test_forgot_and_reset_happy_path(client, app, caplog):
    _user(app)
    import logging

    with caplog.at_level(logging.WARNING):
        res = client.post("/api/v1/forgot-password", json={"email": "reset@example.com"})
    assert res.status_code == 200

    # Extract the token from the dev-mode log.
    import re

    text = caplog.text
    m = re.search(r"token=([A-Za-z0-9_\-]+)", text)
    assert m, "reset token not logged in dev mode"
    token = m.group(1)

    res = client.post("/api/v1/reset-password", json={"token": token, "password": "newpassword1"})
    assert res.status_code == 200, res.get_json()

    # Old password no longer works; new one does.
    assert client.post("/api/v1/login", json={"email": "reset@example.com", "password": "oldpassword1"}).status_code == 401
    assert client.post("/api/v1/login", json={"email": "reset@example.com", "password": "newpassword1"}).status_code == 200


def test_reset_token_single_use(client, app, caplog):
    _user(app, "single@example.com")
    import logging, re

    with caplog.at_level(logging.WARNING):
        client.post("/api/v1/forgot-password", json={"email": "single@example.com"})
    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text).group(1)

    assert client.post("/api/v1/reset-password", json={"token": token, "password": "newpassword1"}).status_code == 200
    # Reuse rejected.
    assert client.post("/api/v1/reset-password", json={"token": token, "password": "anotherpass1"}).status_code == 400


def test_reset_rejects_weak_password(client, app, caplog):
    _user(app, "weak@example.com")
    import logging, re

    with caplog.at_level(logging.WARNING):
        client.post("/api/v1/forgot-password", json={"email": "weak@example.com"})
    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text).group(1)
    res = client.post("/api/v1/reset-password", json={"token": token, "password": "short"})
    assert res.status_code == 400


def test_reset_rejects_invalid_token(client, app):
    res = client.post("/api/v1/reset-password", json={"token": "bogus", "password": "newpassword1"})
    assert res.status_code == 400


def test_validate_reset_token(client, app, caplog):
    _user(app, "val@example.com")
    import logging, re

    with caplog.at_level(logging.WARNING):
        client.post("/api/v1/forgot-password", json={"email": "val@example.com"})
    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text).group(1)
    res = client.get(f"/api/v1/reset-password/validate?token={token}")
    assert res.status_code == 200
    assert res.get_json()["data"]["valid"] is True

    res = client.get("/api/v1/reset-password/validate?token=bogus")
    assert res.status_code == 400