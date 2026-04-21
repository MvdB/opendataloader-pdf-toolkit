from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request


# Configuration — everything is read at import time. Leave these unset and the
# middleware is a no-op, which is the default posture for the sample.
KEYCLOAK_JWKS_URL = os.environ.get("KEYCLOAK_JWKS_URL") or None
KEYCLOAK_AUDIENCE = os.environ.get("KEYCLOAK_AUDIENCE") or None
KEYCLOAK_ISSUER = os.environ.get("KEYCLOAK_ISSUER") or None
KEYCLOAK_REQUIRED_SCOPE = os.environ.get("KEYCLOAK_REQUIRED_SCOPE") or None


# Lazily initialized to keep PyJWT out of the import path for installs that
# don't use the [auth] extra. Tests monkeypatch this directly with a fake.
_jwks_client: Any = None


def _signing_key(token: str) -> Any:
    global _jwks_client
    if _jwks_client is None:
        if KEYCLOAK_JWKS_URL is None:  # pragma: no cover — guarded upstream
            raise RuntimeError("KEYCLOAK_JWKS_URL is not configured")
        from jwt import PyJWKClient  # pyjwt[crypto]; installed via [auth]/[dev] extras
        _jwks_client = PyJWKClient(KEYCLOAK_JWKS_URL)
    return _jwks_client.get_signing_key_from_jwt(token).key


def _verify_token(token: str) -> dict[str, Any]:
    import jwt  # local import so the module loads even without [auth] installed
    options = {
        "verify_aud": KEYCLOAK_AUDIENCE is not None,
        "verify_iss": KEYCLOAK_ISSUER is not None,
    }
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=["RS256"],
            audience=KEYCLOAK_AUDIENCE,
            issuer=KEYCLOAK_ISSUER,
            options=options,
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    if KEYCLOAK_REQUIRED_SCOPE is not None:
        scopes = (claims.get("scope") or "").split()
        if KEYCLOAK_REQUIRED_SCOPE not in scopes:
            raise HTTPException(status_code=403, detail="insufficient scope")
    return claims


async def require_auth(request: Request) -> None:
    """Auth seam — no-op until KEYCLOAK_JWKS_URL is set, OIDC verifier when it is.

    Expects `Authorization: Bearer <token>` on every protected request. Plug in
    other identity providers by setting JWKS/audience/issuer to their equivalents;
    the code is Keycloak-flavored in naming only.
    """
    if KEYCLOAK_JWKS_URL is None:
        return None
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header.split(None, 1)[1].strip()
    _verify_token(token)
    return None
