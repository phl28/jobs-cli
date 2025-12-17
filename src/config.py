"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and config file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bright Data MCP settings
    bright_data_api_token: str = Field(
        default="",
        description="Bright Data API token for MCP access",
    )
    bright_data_mcp_url: str = Field(
        default="https://mcp.brightdata.com/sse",
        description="Bright Data MCP SSE endpoint",
    )
    monthly_request_limit: int = Field(
        default=5000,
        description="Monthly request limit for free tier",
    )

    # Cache settings
    cache_dir: Path = Field(
        default=Path.home() / ".cache" / "jobs-cli",
        description="Directory for cache files",
    )
    cache_expiry_hours: int = Field(
        default=24,
        description="Hours before cached data is considered stale",
    )

    # Search defaults
    default_location: str = Field(
        default="Beijing",
        description="Default location for job searches",
    )
    default_limit: int = Field(
        default=20,
        description="Default number of results to show",
    )
    max_pages_per_platform: int = Field(
        default=3,
        description="Maximum pages to scrape per platform",
    )

    # Enabled scrapers
    enabled_scrapers: list[str] = Field(
        default=["boss_zhipin", "zhaopin", "job51", "liepin"],
        description="List of enabled scraper names",
    )

    @property
    def database_path(self) -> Path:
        """Get the SQLite database path."""
        return self.cache_dir / "jobs.db"

    @property
    def mcp_url_with_token(self) -> str:
        """Get the full MCP URL with token."""
        return f"{self.bright_data_mcp_url}?token={self.bright_data_api_token}"

    def ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings (useful for testing)."""
    global _settings
    _settings = None
