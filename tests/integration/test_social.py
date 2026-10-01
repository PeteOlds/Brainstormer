"""Phase 5: social login flows, linking ceremony, member management."""

import base64
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app.extensions import db
from app.models import Instance, Membership, OAuthIdentity, TenantOAuthConfig, User


def b64url_int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_rsa():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
        "n": b64url_int(numbers.n),
        "e": b64url_int(numbers.e),
    }
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return jwk, pem


def sign_id_token(pem, issuer, audience, subject, email, verified, nonce):
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "sub": subject,
            "email": email,
            "email_verified": verified,
            "nonce": nonce,
            "exp": now + timedelta(minutes=5),
            "iat": now,
        },
        pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


ISSUER = "https://accounts.google.com"
AUDIENCE = "test-client-id"


def setup_instance(email="social-admin@t.test", number=50, name="Social"):
    from app.models import ROLE_INSTANCE_ADMIN, UserRole

    inst = Instance(number=number, name=name)
    db.session.add(inst)
    db.session.flush()
    admin = User(email=email, role=UserRole.ADMIN)
    admin.set_password("password123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(
        Membership(user_id=admin.id, instance_id=inst.id, role=ROLE_INSTANCE_ADMIN)
    )
    db.session.add(
        TenantOAuthConfig(
            instance_id=inst.id, provider_name="google", client_id=AUDIENCE
        )
    )
    db.session.flush()
    TenantOAuthConfig.query.filter_by(
        instance_id=inst.id, provider_name="google"
    ).first().client_secret = "test-secret"
    db.session.commit()
    return str(inst.id)


def start_state(client, iid):
    res = client.get(f"/api/v1/oauth/google/start?instance_id={iid}")
    assert res.status_code == 200, res.get_json()
    query = parse_qs(urlparse(res.get_json()["data"]["auth_url"]).query)
    assert query["client_id"] == [AUDIENCE]
    assert query["code_challenge_method"] == ["S256"]
    return query["state"][0]


def state_nonce(state):
    from app.utils.crypto import get_fernet

    return json.loads(get_fernet().decrypt(state.encode()).decode())["nonce"]


def run_callback(client, state, id_token):
    with (
        patch("app.services.social_auth._http_get", return_value={"keys": [RSA_JWK]}),
        patch(
            "app.services.social_auth._http_post", return_value={"id_token": id_token}
        ),
    ):
        return client.get(f"/api/v1/oauth/google/callback?code=authcode&state={state}")


RSA_JWK, RSA_PEM = make_rsa()


def test_start_flow(app, client):
    with app.app_context():
        iid = setup_instance()
    res = client.get("/api/v1/oauth/google/start")
    assert res.status_code == 400
    res = client.get(
        "/api/v1/oauth/bogus/start?instance_id=00000000-0000-0000-0000-000000000000"
    )
    assert res.status_code == 404
    res = client.get(f"/api/v1/oauth/google/start?instance_id={iid}")
    assert res.status_code == 200

    with app.app_context():
        other = Instance(number=51, name="NoSocial")
        db.session.add(other)
        db.session.commit()
        oid = str(other.id)
    res = client.get(f"/api/v1/oauth/google/start?instance_id={oid}")
    assert res.status_code == 400


def test_callback_new_user_jit(app, client):
    with app.app_context():
        iid = setup_instance()
    # state must be minted over HTTP (Fernet needs app config):
    state = start_state(client, iid)
    nonce = state_nonce(state)
    token = sign_id_token(
        RSA_PEM, ISSUER, AUDIENCE, "google-sub-1", "newbie@example.com", True, nonce
    )
    res = run_callback(client, state, token)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()["data"]
    assert body["user"]["email"] == "newbie@example.com"

    with app.app_context():
        user = User.query.filter_by(email="newbie@example.com").first()
        assert user is not None
        identity = OAuthIdentity.query.filter_by(
            provider="google", subject="google-sub-1"
        ).first()
        assert identity is not None and str(identity.user_id) == str(user.id)
        role = Membership.get_role(user.id, user.memberships.first().instance_id)
        assert role == "USER"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/v1/me", headers=headers).status_code == 200


def test_callback_returning_subject(app, client):
    with app.app_context():
        iid = setup_instance(number=52)
    state = start_state(client, iid)
    token = sign_id_token(
        RSA_PEM,
        ISSUER,
        AUDIENCE,
        "google-sub-2",
        "returner@example.com",
        True,
        state_nonce(state),
    )
    assert run_callback(client, state, token).status_code == 201

    state2 = start_state(client, iid)
    token2 = sign_id_token(
        RSA_PEM,
        ISSUER,
        AUDIENCE,
        "google-sub-2",
        "changed@example.com",
        True,
        state_nonce(state2),
    )
    res = run_callback(client, state2, token2)
    assert res.status_code == 200, res.get_json()
    # Email changed at the provider; the immutable subject still logs in.
    assert res.get_json()["data"]["user"]["email"] == "returner@example.com"


def test_callback_linking_ceremony(app, client):
    with app.app_context():
        iid = setup_instance(number=53)
        user = User(email="linked@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    state = start_state(client, iid)
    token = sign_id_token(
        RSA_PEM,
        ISSUER,
        AUDIENCE,
        "google-sub-3",
        "linked@example.com",
        True,
        state_nonce(state),
    )
    res = run_callback(client, state, token)
    assert res.status_code == 409, res.get_json()
    assert res.get_json()["error_code"] == "LINKING_REQUIRED"
    link_token = res.get_json()["details"]["linking_token"]

    res = client.post("/api/v1/oauth/link", json={"linking_token": link_token})
    assert res.status_code == 400
    res = client.post(
        "/api/v1/oauth/link", json={"linking_token": "bogus", "confirm": True}
    )
    assert res.status_code == 400
    res = client.post(
        "/api/v1/oauth/link", json={"linking_token": link_token, "confirm": True}
    )
    assert res.status_code == 200, res.get_json()

    with app.app_context():
        user = User.query.filter_by(email="linked@example.com").first()
        assert (
            OAuthIdentity.query.filter_by(
                provider="google", subject="google-sub-3", user_id=user.id
            ).first()
            is not None
        )

    # Second login goes straight through.
    state2 = start_state(client, iid)
    token2 = sign_id_token(
        RSA_PEM,
        ISSUER,
        AUDIENCE,
        "google-sub-3",
        "linked@example.com",
        True,
        state_nonce(state2),
    )
    assert run_callback(client, state2, token2).status_code == 200


def test_callback_unverified_email_rejected(app, client):
    with app.app_context():
        iid = setup_instance(number=54)
    state = start_state(client, iid)
    token = sign_id_token(
        RSA_PEM,
        ISSUER,
        AUDIENCE,
        "google-sub-4",
        "unverified@example.com",
        False,
        state_nonce(state),
    )
    res = run_callback(client, state, token)
    assert res.status_code == 400
    with app.app_context():
        assert User.query.filter_by(email="unverified@example.com").first() is None
        assert OAuthIdentity.query.filter_by(subject="google-sub-4").first() is None


def test_callback_bad_state_rejected(app, client):
    with app.app_context():
        iid = setup_instance(number=55)
    state = start_state(client, iid)
    res = client.get("/api/v1/oauth/google/callback?code=x&state=tampered")
    assert res.status_code == 400
    # Cross-provider replay is rejected too.
    res = client.get(f"/api/v1/oauth/microsoft/callback?code=x&state={state}")
    assert res.status_code == 400


def test_oauth_config_hygiene(app, client):
    with app.app_context():
        iid = setup_instance(number=56)
        plain = User(email="plain-soc@t.test")
        plain.set_password("password123")
        db.session.add(plain)
        db.session.commit()
    res = client.post(
        "/api/v1/login", json={"email": "plain-soc@t.test", "password": "password123"}
    )
    plain_h = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}
    assert (
        client.get(f"/api/v1/instances/{iid}/oauth", headers=plain_h).status_code == 404
    )

    res = client.post(
        "/api/v1/login",
        json={
            "email": "social-admin@t.test",
            "password": "password123",
            "instance_id": iid,
        },
    )
    admin_h = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}
    res = client.get(f"/api/v1/instances/{iid}/oauth", headers=admin_h)
    assert res.status_code == 200
    assert "client_secret" not in res.get_data(as_text=True)

    res = client.put(
        f"/api/v1/instances/{iid}/oauth",
        json={
            "provider": "apple",
            "client_id": "com.example.app",
            "client_secret": "apple-jwt-secret",
        },
        headers=admin_h,
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["config"]["has_secret"] is True
    res = client.put(
        f"/api/v1/instances/{iid}/oauth",
        json={"provider": "nope", "client_id": "x"},
        headers=admin_h,
    )
    assert res.status_code == 400


def test_member_management_guards(app, client):
    from app.models import ROLE_INSTANCE_ADMIN, ROLE_USER

    with app.app_context():
        iid = setup_instance(number=57, email="mem-admin@t.test")
        admin = User.query.filter_by(email="mem-admin@t.test").first()
        member = User(email="member@t.test")
        member.set_password("password123")
        db.session.add(member)
        db.session.flush()
        db.session.add(
            Membership(
                user_id=member.id,
                instance_id=admin.memberships.first().instance_id,
                role=ROLE_USER,
            )
        )
        db.session.commit()
        mid = str(member.id)
    res = client.post(
        "/api/v1/login",
        json={
            "email": "mem-admin@t.test",
            "password": "password123",
            "instance_id": iid,
        },
    )
    admin_h = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}

    res = client.get(f"/api/v1/instances/{iid}/members", headers=admin_h)
    assert res.status_code == 200
    assert {m["email"] for m in res.get_json()["data"]["members"]} == {
        "mem-admin@t.test",
        "member@t.test",
    }

    res = client.patch(
        f"/api/v1/instances/{iid}/members/{mid}", json={"role": "BOSS"}, headers=admin_h
    )
    assert res.status_code == 400
    res = client.patch(
        f"/api/v1/instances/{iid}/members/{mid}",
        json={"role": ROLE_INSTANCE_ADMIN},
        headers=admin_h,
    )
    assert res.status_code == 200

    # Cannot remove the last admin, cannot touch yourself.
    with app.app_context():
        from app.services import instances as instance_svc

        site = User(email="site-soc@t.test")
        site.set_password("password123")
        db.session.add(site)
        db.session.commit()
        instance_svc.grant_site_admin(site.id)
        aid = str(User.query.filter_by(email="mem-admin@t.test").first().id)
    res = client.post(
        "/api/v1/login", json={"email": "site-soc@t.test", "password": "password123"}
    )
    site_h = {"Authorization": f"Bearer {res.get_json()['data']['access_token']}"}
    assert (
        client.delete(
            f"/api/v1/instances/{iid}/members/{aid}", headers=admin_h
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/instances/{iid}/members/{mid}", headers=admin_h
        ).status_code
        == 200
    )
    # aid is now the sole admin: even the site admin cannot remove that last grant.
    res = client.delete(f"/api/v1/instances/{iid}/members/{aid}", headers=site_h)
    assert res.status_code == 409
    res = client.patch(
        f"/api/v1/instances/{iid}/members/{aid}",
        json={"role": ROLE_USER},
        headers=site_h,
    )
    assert res.status_code == 409
