import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$wagCPXjifgvUFBzq4hqe3w$"
    "CYaIb8sB+wtD+Vu/P4uod1+Qof8h+1g7bbDlBID48Rc"
)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str | None) -> bool:
    candidate = encoded_hash or DUMMY_PASSWORD_HASH
    valid = password_hash.verify(password, candidate)
    return valid and encoded_hash is not None


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
