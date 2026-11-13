"""Encrypt/decrypt Connection secrets at rest (Fernet, key from env var).

Secrets must never appear in API responses, logs, or Celery task arguments
(Phase 1 finding: the pre-Connections auth_headers path put them in Celery
task args in plaintext). The decrypt side is only ever called inside the
Celery worker, immediately before the HTTP call to the target system.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class ConnectionDecryptionError(Exception):
    """Raised when a stored secret cannot be decrypted with the configured key."""


def _fernet() -> Fernet:
    return Fernet(settings.CONNECTION_ENCRYPTION_KEY.encode("utf-8"))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ConnectionDecryptionError(
            "Impossible de déchiffrer le secret de connexion — clé "
            "CONNECTION_ENCRYPTION_KEY incorrecte ou secret corrompu."
        ) from exc
