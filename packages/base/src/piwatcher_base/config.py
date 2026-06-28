"""Server configuration for PiWatcher base station."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    api_key: str = Field(validation_alias=AliasChoices("PIWATCHER_API_KEY", "API_KEY"))
    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "PIWATCHER_DATABASE_URL")
    )
    frame_storage_path: Path = Field(
        default=Path("/home/bostdiek/piwatcher/frames"),
        validation_alias=AliasChoices("FRAME_STORAGE_PATH", "PIWATCHER_FRAME_STORAGE_PATH"),
    )
    llama_swap_url: str = Field(
        default="http://localhost:8080/v1",
        validation_alias=AliasChoices("LLAMA_SWAP_URL", "PIWATCHER_LLAMA_SWAP_URL"),
    )
    llama_swap_model: str = Field(
        default="lfm2-vl-450m",
        validation_alias=AliasChoices("LLAMA_SWAP_MODEL", "PIWATCHER_LLAMA_SWAP_MODEL"),
    )
    ntfy_topic: str = Field(
        default="piwatcher",
        validation_alias=AliasChoices("NTFY_TOPIC", "PIWATCHER_NTFY_TOPIC"),
    )
    ntfy_url: str = Field(
        default="https://ntfy.sh",
        validation_alias=AliasChoices("NTFY_URL", "PIWATCHER_NTFY_URL"),
    )
    max_inference_temp_c: float = Field(
        default=72.0,
        validation_alias=AliasChoices("MAX_INFERENCE_TEMP_C", "PIWATCHER_MAX_INFERENCE_TEMP_C"),
    )
    cooldown_temp_c: float = Field(
        default=60.0,
        validation_alias=AliasChoices("COOLDOWN_TEMP_C", "PIWATCHER_COOLDOWN_TEMP_C"),
    )
    inference_gap_seconds: int = Field(
        default=15,
        ge=0,
        validation_alias=AliasChoices("INFERENCE_GAP_SECONDS", "PIWATCHER_INFERENCE_GAP_SECONDS"),
    )
    inference_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_INFERENCE", "PIWATCHER_ENABLE_INFERENCE"),
    )
    heartbeat_ttl_days: int = Field(
        default=90,
        ge=1,
        validation_alias=AliasChoices("HEARTBEAT_TTL_DAYS", "PIWATCHER_HEARTBEAT_TTL_DAYS"),
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()  # ty: ignore[missing-argument]
