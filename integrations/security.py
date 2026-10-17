from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet

from core.config import settings


def encrypt_token(token: str) -> str:
    if not settings.token_encryption_key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required to store integration tokens")

    fernet = Fernet(settings.token_encryption_key.encode("utf-8"))
    return fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decrypt_token(token: str) -> str:
    if not settings.token_encryption_key:
        raise RuntimeError("Token encryption configuration is missing")
    try:
        return Fernet(settings.token_encryption_key.encode()).decrypt(token.encode()).decode()
    except Exception:
        raise RuntimeError("Cannot decrypt integration credential") from None
