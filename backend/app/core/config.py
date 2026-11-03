from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTONOMUS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    allow_remote_access: bool = False

    data_dir: Path = BASE_DIR / "data"
    log_dir: Path = BASE_DIR / "logs"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_max_bytes: int = Field(default=1_048_576, ge=1024)
    log_backup_count: int = Field(default=3, ge=0)

    task_queue_capacity: int = Field(default=100, ge=1, le=10000)
    task_max_concurrency: int = Field(default=2, ge=1, le=16)
    task_default_timeout: float = Field(default=30.0, gt=0, le=3600)
    task_max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_delay: float = Field(default=0.1, gt=0)
    retry_max_delay: float = Field(default=5.0, gt=0)
    scheduler_poll_interval: float = Field(default=0.1, gt=0)
    shutdown_timeout: float = Field(default=10.0, gt=0)

    memory_percent_max: float = Field(default=90.0, gt=0, le=100)
    disk_percent_max: float = Field(default=90.0, gt=0, le=100)
    cpu_percent_max: float = Field(default=95.0, gt=0, le=100)

    session_ttl_minutes: int = Field(default=60, ge=1, le=1440)
    login_rate_limit: int = Field(default=5, ge=1, le=100)
    docs_enabled: bool = True
    # Lifetime of the approval that gates an approval_required task. Bounded so a
    # gated task can never wait on an immortal approval: on expiry the task is
    # cancelled by the scheduler sweep rather than left in WAITING_FOR_APPROVAL.
    task_approval_ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    external_execution_enabled: bool = False
    financial_execution_enabled: bool = False
    cloud_ai_enabled: bool = False

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("P-01 backend must bind to loopback; remote access is not implemented")
        return v

    @model_validator(mode="after")
    def validate_phase_flags(self) -> "Settings":
        if self.allow_remote_access:
            raise ValueError("Remote access requires a later approved security design")
        if self.external_execution_enabled or self.financial_execution_enabled or self.cloud_ai_enabled:
            raise ValueError("External, financial and cloud AI execution are disabled in P-01")
        if self.retry_max_delay < self.retry_base_delay:
            raise ValueError("retry_max_delay must be >= retry_base_delay")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "autonomus.db"

    @property
    def async_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"

    @property
    def sync_database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def get_settings() -> Settings:
    return Settings()
