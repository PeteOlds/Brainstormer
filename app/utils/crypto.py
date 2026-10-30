import base64
import logging

from cryptography.fernet import Fernet

from app.config import Config

logger = logging.getLogger(__name__)


def _configured_key() -> str | bytes:
    """The key from the running app, falling back to the class config.

    Reading `Config.FERNET_KEY` directly (as this module used to) ignored
    app-level overrides, so tests and restores could encrypt with a
    different key than the process that wrote the ciphertext.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context() and "FERNET_KEY" in current_app.config:
            # An explicit (even empty) app-level value wins over the class
            # default: that is how a caller disables or overrides the key.
            return current_app.config["FERNET_KEY"] or ""
    except Exception:  # pragma: no cover - Flask import always works here
        pass
    return Config.FERNET_KEY


def get_fernet() -> Fernet:
    """Build a Fernet from FERNET_KEY, refusing weak or missing keys.

    The previous version padded any short key with zero bytes, which turned
    a typo (or an empty value) into a valid-looking but predictable key —
    silently weakening every stored secret (PATs, OAuth secrets, API keys).
    """
    key = _configured_key()
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not configured. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    raw = key.encode() if isinstance(key, str) else key

    # Preferred form: a 44-character urlsafe-base64 key (what Fernet emits).
    try:
        if len(base64.urlsafe_b64decode(raw)) == 32:
            return Fernet(raw)
    except Exception:
        pass

    # Backwards compatibility: a raw 32-byte secret.
    if len(raw) == 32:
        return Fernet(base64.urlsafe_b64encode(raw))

    raise RuntimeError(
        "FERNET_KEY must be a 32-byte value or a 44-character urlsafe-base64 "
        f"key; got {len(raw)} bytes. Refusing to pad a weak key."
    )


def encrypt(plaintext: str) -> str:
    """Encrypt a string using Fernet."""
    if not plaintext:
        return ""
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a string using Fernet.

    A failed decrypt returns "" (callers treat a missing secret as
    unconfigured), but it is logged: silently swallowing the error hid
    wrong-key and corruption bugs.
    """
    if not ciphertext:
        return ""
    f = get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception as exc:
        logger.warning(
            "decrypt failed (%s): stored secret is unreadable with the "
            "current FERNET_KEY",
            type(exc).__name__,
        )
        return ""
