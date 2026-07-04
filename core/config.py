"""Project configuration.

Loads environment variables from .env and exposes typed settings
used by the rest of the WB Profit Bot project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    supabase_service_role_key: str | None
    wb_api_key: str | None
    telegram_bot_token: str | None
    telegram_bot_username: str | None
    app_base_url: str | None
    shopify_client_id: str | None
    shopify_client_secret: str | None
    shopify_redirect_uri: str | None
    shopify_scopes: str
    token_encryption_key: str | None
    oauth_state_ttl_seconds: int
    environment: str = "local"
    log_level: str = "INFO"


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _get_optional_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


settings = Settings(
    supabase_url=_get_required_env("SUPABASE_URL"),
    supabase_key=_get_required_env("SUPABASE_KEY"),
    supabase_service_role_key=_get_optional_env("SUPABASE_SERVICE_ROLE_KEY"),
    wb_api_key=_get_optional_env("WB_API_KEY"),
    telegram_bot_token=_get_optional_env("TELEGRAM_BOT_TOKEN"),
    telegram_bot_username=_get_optional_env("TELEGRAM_BOT_USERNAME"),
    app_base_url=_get_optional_env("APP_BASE_URL"),
    shopify_client_id=_get_optional_env("SHOPIFY_CLIENT_ID"),
    shopify_client_secret=_get_optional_env("SHOPIFY_CLIENT_SECRET"),
    shopify_redirect_uri=_get_optional_env("SHOPIFY_REDIRECT_URI"),
    shopify_scopes=_get_optional_env(
        "SHOPIFY_SCOPES",
        "read_products,read_orders,read_inventory",
    ) or "read_products,read_orders,read_inventory",
    token_encryption_key=_get_optional_env("TOKEN_ENCRYPTION_KEY"),
    oauth_state_ttl_seconds=int(
        _get_optional_env("OAUTH_STATE_TTL_SECONDS", "600") or "600"
    ),
    environment=_get_optional_env("ENVIRONMENT", "local") or "local",
    log_level=_get_optional_env("LOG_LEVEL", "INFO") or "INFO",
)


# Backward-compatible constants for older files in the project.
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_key
SUPABASE_SERVICE_ROLE_KEY = settings.supabase_service_role_key
WB_API_KEY = settings.wb_api_key
TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
TELEGRAM_BOT_USERNAME = settings.telegram_bot_username
APP_BASE_URL = settings.app_base_url
SHOPIFY_CLIENT_ID = settings.shopify_client_id
SHOPIFY_CLIENT_SECRET = settings.shopify_client_secret
SHOPIFY_REDIRECT_URI = settings.shopify_redirect_uri
SHOPIFY_SCOPES = settings.shopify_scopes
TOKEN_ENCRYPTION_KEY = settings.token_encryption_key
OAUTH_STATE_TTL_SECONDS = settings.oauth_state_ttl_seconds
ENVIRONMENT = settings.environment
LOG_LEVEL = settings.log_level
