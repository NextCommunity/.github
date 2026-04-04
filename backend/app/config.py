"""Application configuration loaded from environment variables."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Backend configuration.

    All values can be overridden via environment variables.
    """

    org_name: str = os.getenv("ORG_NAME", "NextCommunity")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    api_key: str = os.getenv("API_KEY", "")
    cache_ttl: int = int(os.getenv("CACHE_TTL", "900"))  # 15 minutes
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "info")
    levels_json_url: str = os.getenv(
        "LEVELS_JSON_URL",
        "https://raw.githubusercontent.com/NextCommunity/"
        "NextCommunity.github.io/main/src/_data/levels.json",
    )


settings = Settings()
