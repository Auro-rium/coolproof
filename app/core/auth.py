from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import ClassVar

import jwt
from jwt import PyJWKClient
from jwt.types import Options

from app.core.config import Settings
from app.core.errors import APIError


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    email: str | None
    roles: frozenset[str] = frozenset()


class CognitoJWTVerifier:
    _jwks_clients: ClassVar[dict[str, PyJWKClient]] = {}

    def __init__(self, settings: Settings):
        self.settings = settings

    async def verify(self, token: str) -> TokenClaims:
        issuer = self.settings.resolved_cognito_issuer
        jwks_url = self.settings.resolved_cognito_jwks_url
        if not issuer or not jwks_url:
            raise APIError(503, "auth_not_configured", "Cognito authentication is not configured")
        try:
            client = self._jwks_clients.setdefault(
                jwks_url, PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
            )
            signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
            audience = self.settings.cognito_jwt_audience or self.settings.cognito_app_client_id
            options: Options = {"verify_aud": bool(audience)}
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=issuer,
                audience=audience,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise APIError(401, "invalid_token", "Bearer token validation failed") from exc
        if payload.get("token_use") not in {"access", "id"} or not payload.get("sub"):
            raise APIError(401, "invalid_token", "Token claims are incomplete")
        raw_groups = payload.get("cognito:groups", payload.get("groups", []))
        if isinstance(raw_groups, str):
            raw_groups = raw_groups.split(",")
        roles = frozenset(str(item).casefold() for item in raw_groups if isinstance(item, str))
        return TokenClaims(subject=payload["sub"], email=payload.get("email"), roles=roles)
