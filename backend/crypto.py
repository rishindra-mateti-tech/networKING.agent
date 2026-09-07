import base64
import hashlib

from cryptography.fernet import Fernet
from sqlalchemy.types import TypeDecorator, Text

from config import ENCRYPTION_KEY


def _derive_fernet_key(secret: str) -> bytes:
    """Fernet requires a 32-byte url-safe base64 key; derive one from our raw secret."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key(ENCRYPTION_KEY))


def encrypt_value(plaintext: str) -> str:
    if plaintext is None:
        return None
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    if ciphertext is None:
        return None
    return _fernet.decrypt(ciphertext.encode()).decode()


def is_encrypted(value: str) -> bool:
    """Best-effort check used by the migration to skip already-encrypted values."""
    if not value:
        return False
    try:
        _fernet.decrypt(value.encode())
        return True
    except Exception:
        return False


class EncryptedString(TypeDecorator):
    """Transparently encrypts values at rest (Fernet/AES) and decrypts on read."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)
