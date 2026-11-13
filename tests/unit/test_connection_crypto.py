import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.connections.crypto import ConnectionDecryptionError, decrypt_secret, encrypt_secret
from app.core.config import Settings


def test_encrypt_decrypt_round_trip():
    plaintext = "super-secret-api-key-value"
    token = encrypt_secret(plaintext)

    assert token != plaintext
    assert decrypt_secret(token) == plaintext


def test_decrypt_fails_with_wrong_key(monkeypatch):
    from app.connections import crypto

    token = encrypt_secret("another-secret")

    monkeypatch.setattr(crypto.settings, "CONNECTION_ENCRYPTION_KEY", Fernet.generate_key().decode())

    with pytest.raises(ConnectionDecryptionError):
        decrypt_secret(token)


def test_settings_rejects_malformed_connection_encryption_key(monkeypatch):
    monkeypatch.setenv("CONNECTION_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_accepts_valid_connection_encryption_key(monkeypatch):
    monkeypatch.setenv("CONNECTION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings(_env_file=None)
    assert settings.CONNECTION_ENCRYPTION_KEY
