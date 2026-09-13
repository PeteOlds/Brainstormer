import base64
from cryptography.fernet import Fernet
from app.config import Config


# Fernet key should be 32 bytes base64 encoded
# Get from config
def get_fernet() -> Fernet:
    key = Config.FERNET_KEY
    if isinstance(key, str):
        key = key.encode()
    # Ensure key is 32 bytes
    if len(key) != 32:
        # If it's base64 encoded, decode it
        try:
            key = base64.urlsafe_b64decode(key)
        except Exception:
            # Pad or truncate to 32 bytes
            key = key.ljust(32, b'0')[:32]
    return Fernet(base64.urlsafe_b64encode(key[:32]))


def encrypt(plaintext: str) -> str:
    """Encrypt a string using Fernet."""
    if not plaintext:
        return ""
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a string using Fernet."""
    if not ciphertext:
        return ""
    f = get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""