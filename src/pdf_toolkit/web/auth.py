from __future__ import annotations

from fastapi import Request


async def require_auth(request: Request) -> None:
    """Auth seam — replace with Keycloak/OIDC verification without touching route bodies."""
    return None
