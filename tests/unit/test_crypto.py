"""Fernet key handling: a weak key must fail loudly, never be padded."""

import pytest
from cryptography.fernet import Fernet

from app.utils import crypto


@pytest.fixture()
def ctx(app):
    """Crypto reads the running app's config, so tests need a context."""
    with app.app_context():
        yield app


def test_missing_key_is_rejected(ctx):
    ctx.config["FERNET_KEY"] = ""
    with pytest.raises(RuntimeError):
        crypto.get_fernet()


def test_short_key_is_rejected(ctx):
    """`get_fernet` used to zero-pad any short key into a valid one."""
    ctx.config["FERNET_KEY"] = "changeme"
    with pytest.raises(RuntimeError):
        crypto.get_fernet()


def test_accepts_urlsafe_base64_key(ctx):
    ctx.config["FERNET_KEY"] = Fernet.generate_key().decode()
    fernet = crypto.get_fernet()
    assert fernet.decrypt(fernet.encrypt(b"hello")) == b"hello"


def test_accepts_raw_32_byte_key(ctx):
    ctx.config["FERNET_KEY"] = "k" * 32
    fernet = crypto.get_fernet()
    assert fernet.decrypt(fernet.encrypt(b"hello")) == b"hello"


def test_round_trip(ctx):
    ctx.config["FERNET_KEY"] = Fernet.generate_key().decode()
    assert crypto.decrypt(crypto.encrypt("top secret")) == "top secret"


def test_tampered_ciphertext_is_reported(ctx, caplog):
    ctx.config["FERNET_KEY"] = Fernet.generate_key().decode()
    token = crypto.encrypt("top secret")
    tampered = token[:-4] + "AAAA"

    with caplog.at_level("WARNING"):
        assert crypto.decrypt(tampered) == ""
    assert "decrypt" in caplog.text.lower()
