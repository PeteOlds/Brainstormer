"""Social login OIDC flows (Phase 5): Google, Apple, Microsoft.

Stateless PKCE: the `state` param is a Fernet-encrypted bundle
(instance, provider, verifier, nonce) with a 10-minute TTL — no server
storage, nothing to clean up. HTTP is isolated in _http_post/_http_get
so tests can stub the providers. Secrets and codes never enter logs.
"""

import base64
import hashlib
import json
import secrets
import structlog
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()

STATE_TTL_SECONDS = 600

PROVIDER_META = {
    "google": {
        "issuer": "https://accounts.google.com",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "jwks_url": "https://www.googleapis.com/oauth2/v3/certs",
        "scope": "openid email profile",
    },
    "microsoft": {
        "issuer_prefix": "https://login.microsoftonline.com/",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "jwks_url": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        "scope": "openid email profile",
    },
    "apple": {
        "issuer": "https://appleid.apple.com",
        "auth_url": "https://appleid.apple.com/auth/authorize",
        "token_url": "https://appleid.apple.com/auth/token",
        "jwks_url": "https://appleid.apple.com/auth/keys",
        "scope": "openid email name",
    },
}


class SocialError(ValueError):
    pass


@dataclass(frozen=True)
class SocialProfile:
    provider: str
    subject: str
    email: str
    name: str | None = None


def _http_post(url: str, data: dict) -> dict:
    import httpx

    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, data=data)
        response.raise_for_status()
        return dict(response.json())


def _http_get(url: str) -> dict:
    import httpx

    with httpx.Client(timeout=15.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return dict(response.json())


def _fernet():
    from app.utils.crypto import get_fernet

    return get_fernet()


def _pkce_pair() -> tuple:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_start_url(
    provider: str, instance_id: str, client_id: str, redirect_uri: str
) -> dict:
    """Authorisation URL + opaque state for one login attempt."""
    meta = PROVIDER_META.get(provider)
    if meta is None:
        raise SocialError(f"Unknown provider: {provider}.")
    verifier, challenge = _pkce_pair()
    nonce = secrets.token_urlsafe(16)
    state = (
        _fernet()
        .encrypt(
            json.dumps(
                {
                    "instance_id": str(instance_id),
                    "provider": provider,
                    "verifier": verifier,
                    "nonce": nonce,
                }
            ).encode()
        )
        .decode()
    )
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": meta["scope"],
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider == "apple":
        params["response_mode"] = "query"
    return {
        "auth_url": f"{meta['auth_url']}?{urlencode(params)}",
        "expires_in": STATE_TTL_SECONDS,
    }


def read_state(state: str, provider: str) -> dict:
    try:
        bundle = json.loads(
            _fernet().decrypt(state.encode(), ttl=STATE_TTL_SECONDS).decode()
        )
    except Exception as exc:
        raise SocialError("Login session expired or invalid. Start again.") from exc
    if bundle.get("provider") != provider or not bundle.get("instance_id"):
        raise SocialError("Login session does not match this provider.")
    return dict(bundle)


def _verify_id_token(provider: str, id_token: str, client_id: str, nonce: str) -> dict:
    import jwt as pyjwt

    meta = PROVIDER_META[provider]
    header = pyjwt.get_unverified_header(id_token)
    jwks = _http_get(meta["jwks_url"])
    key_data = next(
        (k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None
    )
    if key_data is None:
        raise SocialError("Provider key rotation in progress. Try again.")
    key: Any = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    try:
        claims = pyjwt.decode(
            id_token,
            key=key,
            algorithms=["RS256"],
            audience=client_id,
            options={"require": ["exp", "iss", "sub"]},
        )
    except Exception as exc:
        raise SocialError(f"Invalid identity token: {exc}") from exc
    issuer = claims.get("iss", "")
    if "issuer" in meta:
        if issuer != meta["issuer"]:
            raise SocialError("Unexpected token issuer.")
    elif not issuer.startswith(meta["issuer_prefix"]):
        raise SocialError("Unexpected token issuer.")
    if claims.get("nonce") != nonce:
        raise SocialError("Nonce mismatch. Start again.")
    return claims


def _verified_email(provider: str, claims: dict) -> str:
    email = (
        (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    )
    if not email:
        raise SocialError("The provider did not share an email address.")
    verified = claims.get("email_verified", False)
    if isinstance(verified, str):
        verified = verified.lower() == "true"
    if provider == "microsoft" and "email" in claims:
        verified = True
    if not verified:
        raise SocialError("A verified email address is required.")
    return email


def exchange_code(
    provider: str,
    code: str,
    state: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> tuple:
    """Full callback: state -> tokens -> verified profile (no accounts touched).

    Returns (profile, instance_id) so the caller keeps the tenant context
    the flow started with.
    """
    """Full callback: state -> tokens -> verified profile (no accounts touched)."""
    meta = PROVIDER_META.get(provider)
    if meta is None:
        raise SocialError(f"Unknown provider: {provider}.")
    bundle = read_state(state, provider)
    try:
        tokens = _http_post(
            meta["token_url"],
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": bundle["verifier"],
            },
        )
    except Exception as exc:
        raise SocialError(f"Code exchange failed: {exc}") from exc
    id_token = tokens.get("id_token")
    if not id_token:
        raise SocialError("Provider returned no identity token.")
    claims = _verify_id_token(provider, id_token, client_id, bundle["nonce"])
    email = _verified_email(provider, claims)
    logger.info(
        "social_profile_verified",
        provider=provider,
        instance_id=bundle["instance_id"],
        email_hash=hashlib.sha256(email.encode()).hexdigest()[:16],
    )
    return (
        SocialProfile(
            provider=provider,
            subject=str(claims["sub"]),
            email=email,
            name=claims.get("name"),
        ),
        bundle["instance_id"],
    )


def linking_token(
    user_id: Any, provider: str, subject: str, email: str, instance_id: Any
) -> str:
    """Short-lived signed token for the explicit link-confirmation step."""
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt
    from flask import current_app

    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            "type": "oauth_link",
            "sub": str(user_id),
            "provider": provider,
            "subject": subject,
            "email": email,
            "instance_id": str(instance_id),
            "exp": now + timedelta(minutes=10),
            "iat": now,
        },
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )


def read_linking_token(raw: str) -> dict:
    import jwt as pyjwt
    from flask import current_app

    try:
        data = pyjwt.decode(
            raw, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
        )
    except Exception as exc:
        raise SocialError("Link token expired or invalid.") from exc
    if data.get("type") != "oauth_link":
        raise SocialError("Not a link token.")
    return data
