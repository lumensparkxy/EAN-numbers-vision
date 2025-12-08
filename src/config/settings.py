"""
Application settings using Pydantic Settings.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        # Prefer local overrides while keeping .env as the default source
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["dev", "staging", "prod"] = "dev"

    # Azure Storage
    azure_storage_connection_string: SecretStr | None = None
    azure_storage_account_url: str | None = None
    azure_storage_container: str = "product-images"

    # Azure Key Vault
    azure_keyvault_url: str | None = None

    # MongoDB
    mongodb_uri: SecretStr = Field(..., description="MongoDB connection string")
    mongodb_database: str = "ean-extraction-dev"

    # Google Gemini (using new google-genai SDK)
    # Available models: gemini-3-pro-preview, gemini-3-pro-image-preview, gemini-2.5-flash
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3-pro-preview"
    gemini_max_tokens: int = 1024
    gemini_temperature: float = 1.0  # Gemini 3 recommends temperature=1.0
    gemini_timeout: int = 30

    # Worker Configuration
    worker_poll_interval: int = Field(5, description="Seconds between job polls")
    worker_batch_size: int = Field(10, description="Max jobs per batch")
    worker_max_retries: int = Field(3, description="Max retry attempts")

    # Preprocessing
    preprocess_max_dimension: int = Field(2048, description="Max image dimension in pixels")
    preprocess_denoise_strength: int = Field(10, description="Denoise filter strength")

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Manual Review UI
    review_ui_host: str = "0.0.0.0"
    review_ui_port: int = 8000

    # Retention
    retention_days: int = Field(90, description="Days to retain processed images")

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "prod"

    @property
    def mongodb_uri_str(self) -> str:
        """Get MongoDB URI as string."""
        return self.mongodb_uri.get_secret_value()

    @property
    def azure_connection_string_str(self) -> str | None:
        """Get Azure Storage connection string as string."""
        if self.azure_storage_connection_string:
            return self.azure_storage_connection_string.get_secret_value()
        return None

    @property
    def gemini_api_key_str(self) -> str | None:
        """Get Gemini API key as string."""
        if self.gemini_api_key:
            return self.gemini_api_key.get_secret_value()
        return None


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
