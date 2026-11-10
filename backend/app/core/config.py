"""Centralized, validated configuration (P-01 §5).

All settings come from environment variables with the ``AUTONOMUS_`` prefix
(or a local ``.env`` file). Secrets are never logged: :func:`redacted_dict`
masks every field whose name looks sensitive.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_FIELD_HINTS = ("password", "token", "secret", "key", "proxy")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTONOMUS_", env_file=".env", extra="ignore")

    # Application
    app_name: str = "AUTONOMUS Core OS"
    environment: str = Field(default="development", pattern="^(development|production|test)$")
    mode: str = Field(default="simulation", pattern="^(simulation|supervised|controlled|emergency)$")
    host: str = "127.0.0.1"  # loopback by default (P-01 §13.14)
    port: int = Field(default=8000, ge=1, le=65535)

    # Paths / database
    data_dir: Path = Path("data")
    database_url: str | None = None  # derived from data_dir when unset
    auto_migrate: bool = True

    # Logging
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_file: str | None = None  # derived: <data_dir>/../logs/autonomus.log when unset
    log_max_bytes: int = Field(default=1_000_000, ge=10_000)
    log_backup_count: int = Field(default=5, ge=0)

    # Tasks
    queue_capacity: int = Field(default=100, ge=1)
    max_concurrency: int = Field(default=4, ge=1)
    shutdown_timeout_seconds: float = Field(default=10.0, ge=0)
    retry_base_delay_seconds: float = Field(default=0.5, ge=0)
    retry_max_delay_seconds: float = Field(default=30.0, ge=0)

    # Monitoring thresholds (percent)
    cpu_threshold_percent: float = Field(default=90.0, gt=0, le=100)
    memory_threshold_percent: float = Field(default=90.0, gt=0, le=100)
    disk_threshold_percent: float = Field(default=95.0, gt=0, le=100)
    block_nonessential_on_threshold: bool = True

    # Events
    event_rate_limit_per_second: int = Field(default=200, ge=1)
    event_max_depth: int = Field(default=3, ge=1)

    # Intelligence / model providers (P-02). Local-first: Ollama is the
    # default provider candidate; cloud is DISABLED unless the owner
    # explicitly enables it (ADR-001). No default model is named anywhere:
    # model ids live in owner-editable model_profiles rows and start empty
    # because the owner's hardware is not yet known (P-00 carried item).
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = Field(default=3.0, gt=0)
    llm_plan_timeout_seconds: float = Field(default=30.0, gt=0)
    cloud_ai_enabled: bool = False

    # Speech (Expansion F03). Local-first: the one real provider
    # candidate is faster-whisper on the owner's machine; the model
    # (size name or local directory) is owner configuration and
    # starts UNSET — no speech model is named or downloaded by
    # default, and the provider honestly reports unavailable until
    # the library and a model exist (DEF-A2).
    whisper_model: str | None = None

    # Research source acquisition (P-03). Fetching is restricted to
    # registered sources; the optional explicit proxy exists for sandboxes
    # whose egress requires one (unset on a normal owner machine). Its
    # value may embed credentials, so 'proxy' is a redaction hint above.
    research_http_timeout_seconds: float = Field(default=10.0, gt=0)
    research_proxy_url: str | None = None
    research_max_fetch_bytes: int = Field(default=512_000, ge=10_000)
    # Test/staging-only escape hatch for the SSRF guard; production refuses it.
    research_allow_private_hosts: bool = False

    # Auth (see app.core.auth for the full scheme documentation)
    admin_username: str = "owner"
    admin_password: str | None = None  # plaintext ONLY via env; stored scrypt-hashed at first run
    dev_token: str | None = None  # local-dev fallback credential (owner-equivalent)
    service_token: str | None = None  # limited Service principal credential
    session_expiry_hours: float = Field(default=12.0, gt=0)
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    @field_validator("host")
    @classmethod
    def _host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if self.max_concurrency > self.queue_capacity:
            raise ValueError("max_concurrency must not exceed queue_capacity")
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError("retry_max_delay_seconds must be >= retry_base_delay_seconds")
        if self.environment == "production" and not self.admin_password and not self.dev_token:
            raise ValueError(
                "production requires AUTONOMUS_ADMIN_PASSWORD (or a dev token during staging)"
            )
        if self.environment == "production" and self.research_allow_private_hosts:
            raise ValueError(
                "research_allow_private_hosts must never be enabled in production (SSRF guard)"
            )
        return self

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.data_dir / "autonomus.db").resolve()
        return f"sqlite:///{db_path}"

    @property
    def effective_log_file(self) -> Path:
        if self.log_file:
            return Path(self.log_file)
        return (self.data_dir.parent / "logs" / "autonomus.log").resolve()

    def redacted_dict(self) -> dict:
        out: dict = {}
        for key, value in self.model_dump().items():
            if any(hint in key for hint in SECRET_FIELD_HINTS) and value:
                out[key] = "***REDACTED***"
            else:
                out[key] = value
        return out
