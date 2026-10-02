from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def encrypt_credential(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise ValueError("Stored credential cannot be decrypted") from error


def _fernet() -> Fernet:
    key = get_settings().credential_encryption_key
    if not key:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as error:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key"
        ) from error