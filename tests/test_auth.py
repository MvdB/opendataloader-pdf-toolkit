from __future__ import annotations

import importlib
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def rsa_keypair() -> tuple[Any, bytes]:
    """Generate a one-off RSA keypair; return (private-key-object, public-pem-bytes)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


def _mint(private_key: Any, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "aud": "pdf-toolkit",
        "iss": "https://kc.example/realms/test",
        "sub": "user@example.com",
        "scope": "pdf:read",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
    }
    claims.update(overrides)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(claims, private_pem, algorithm="RS256")


def _configured_auth_module(
    monkeypatch: pytest.MonkeyPatch,
    public_pem: bytes,
    *,
    audience: str | None = "pdf-toolkit",
    issuer: str | None = "https://kc.example/realms/test",
    required_scope: str | None = None,
):
    monkeypatch.setenv("KEYCLOAK_JWKS_URL", "http://fake-jwks.invalid/certs")
    if audience is not None:
        monkeypatch.setenv("KEYCLOAK_AUDIENCE", audience)
    else:
        monkeypatch.delenv("KEYCLOAK_AUDIENCE", raising=False)
    if issuer is not None:
        monkeypatch.setenv("KEYCLOAK_ISSUER", issuer)
    else:
        monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    if required_scope is not None:
        monkeypatch.setenv("KEYCLOAK_REQUIRED_SCOPE", required_scope)
    else:
        monkeypatch.delenv("KEYCLOAK_REQUIRED_SCOPE", raising=False)

    from pdf_toolkit.web import auth as auth_module
    importlib.reload(auth_module)

    class _FakeKey:
        def __init__(self, key: bytes) -> None:
            self.key = key

    class _FakeJWKSClient:
        def get_signing_key_from_jwt(self, _token: str) -> _FakeKey:
            return _FakeKey(public_pem)

    monkeypatch.setattr(auth_module, "_jwks_client", _FakeJWKSClient())
    return auth_module


def _client_with(auth_module) -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected(_: None = Depends(auth_module.require_auth)) -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_noop_when_jwks_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEYCLOAK_JWKS_URL", raising=False)
    from pdf_toolkit.web import auth as auth_module
    importlib.reload(auth_module)
    client = _client_with(auth_module)
    # No header required when auth isn't configured.
    r = client.get("/protected")
    assert r.status_code == 200


def test_valid_token_accepted(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[Any, bytes]) -> None:
    private_key, public_pem = rsa_keypair
    auth_module = _configured_auth_module(monkeypatch, public_pem)
    client = _client_with(auth_module)
    token = _mint(private_key)
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_missing_header_rejected(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[Any, bytes]) -> None:
    _, public_pem = rsa_keypair
    auth_module = _configured_auth_module(monkeypatch, public_pem)
    client = _client_with(auth_module)
    r = client.get("/protected")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing bearer token"


def test_wrong_audience_rejected(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[Any, bytes]) -> None:
    private_key, public_pem = rsa_keypair
    auth_module = _configured_auth_module(monkeypatch, public_pem, audience="pdf-toolkit")
    client = _client_with(auth_module)
    token = _mint(private_key, aud="something-else")
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "invalid token" in r.json()["detail"]


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[Any, bytes]) -> None:
    private_key, public_pem = rsa_keypair
    auth_module = _configured_auth_module(monkeypatch, public_pem)
    client = _client_with(auth_module)
    token = _mint(private_key, exp=int(time.time()) - 10)
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_required_scope_enforced(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[Any, bytes]) -> None:
    private_key, public_pem = rsa_keypair
    auth_module = _configured_auth_module(monkeypatch, public_pem, required_scope="pdf:admin")
    client = _client_with(auth_module)
    # Token has "pdf:read" but we're asking for "pdf:admin"
    token = _mint(private_key)
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json()["detail"] == "insufficient scope"


def test_required_scope_satisfied(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[Any, bytes]) -> None:
    private_key, public_pem = rsa_keypair
    auth_module = _configured_auth_module(monkeypatch, public_pem, required_scope="pdf:read")
    client = _client_with(auth_module)
    token = _mint(private_key)
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
