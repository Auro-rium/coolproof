from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are read from the environment only."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="COOLPROOF_", extra="ignore")

    app_name: str = "CoolProof API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./coolproof.db"
    cognito_region: str | None = None
    cognito_user_pool_id: str | None = None
    cognito_app_client_id: str | None = None
    cognito_issuer: str | None = None
    cognito_jwks_url: str | None = None
    cognito_jwt_audience: str | None = None
    cognito_jwt_secret: SecretStr | None = None
    allow_development_auth: bool = True
    metrics_token: SecretStr | None = None
    fortyguard_base_url: str | None = None
    fortyguard_api_key: SecretStr | None = None
    fortyguard_timeout_seconds: float = 30.0
    fortyguard_poll_interval_seconds: float = 2.0
    fortyguard_max_attempts: int = 5
    heat_cache_ttl_seconds: int = 86400
    redis_url: str | None = None
    aws_region: str = "us-east-2"
    documents_bucket: str | None = None

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.lower().strip()

    @property
    def is_development(self) -> bool:
        return self.environment in {"development", "test", "local"}

    @property
    def resolved_cognito_issuer(self) -> str | None:
        if self.cognito_issuer:
            return self.cognito_issuer.rstrip("/")
        if self.cognito_region and self.cognito_user_pool_id:
            return f"https://cognito-idp.{self.cognito_region}.amazonaws.com/{self.cognito_user_pool_id}"
        return None

    @property
    def resolved_cognito_jwks_url(self) -> str | None:
        if self.cognito_jwks_url:
            return self.cognito_jwks_url
        issuer = self.resolved_cognito_issuer
        return f"{issuer}/.well-known/jwks.json" if issuer else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
