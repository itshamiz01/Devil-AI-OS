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
    # Optional external database URL, e.g. a Supabase/Postgres connection string.
    # Unset keeps the local SQLite database, which remains the default and the
    # only backend the full test suite exercises. When set, both the async and
    # the sync engine target it with the driver normalised to psycopg3, which
    # serves SQLAlchemy's sync and async APIs from one package.
    database_url: str | None = None
    # Migrations must not run through a transaction pooler: pgbouncer in
    # transaction mode breaks multi-statement DDL. When this is set it is used
    # for Alembic only, while the runtime engines keep the pooled URL above.
    database_url_direct: str | None = None
    # Applying the whole chain on every serverless cold start is slow, and two
    # cold starts at once can race on the same revision, so a hosted deployment
    # can turn it off and apply migrations deliberately instead.
    run_migrations_on_startup: bool = True
    log_dir: Path = BASE_DIR / "logs"
    backup_dir: Path = BASE_DIR / "backups"
    # Number of most-recent database backups retained before pruning. Bounded so
    # backups cannot silently consume the disk the monitor is watching.
    backup_retention_count: int = Field(default=7, ge=1, le=100)
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

    # ---- P-02 Master Intelligence Engine ----
    # The engine is functional with no model installed: interpretation, planning,
    # scoring, risk classification and orchestration are deterministic. These
    # settings control inference, not whether the engine works.
    intelligence_enabled: bool = True
    # "none" is the honest default for this hardware: no inference runtime is
    # installed. Selecting "ollama" registers an adapter but does not download
    # weights; a model must already be present locally.
    model_provider: Literal["none", "ollama"] = "none"
    registered_model_id: str = ""
    registered_model_context_window: int = Field(default=4096, ge=512, le=2_000_000)
    registered_model_min_ram_gb: float = Field(default=1.0, ge=0.0, le=64.0)
    ollama_base_url: str = "http://127.0.0.1:11434"
    inference_max_concurrent: int = Field(default=1, ge=1, le=8)
    inference_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    # Fraction of *available* RAM one model may be assumed to need. Below 1.0 so
    # inference cannot starve the Core OS of memory.
    inference_ram_safety_fraction: float = Field(default=0.8, gt=0, le=1.0)
    inference_max_cost_per_1k_tokens: float = Field(default=0.0, ge=0.0, le=100.0)
    # Cloud inference stays gated by cloud_ai_enabled above, which the phase-flag
    # validator refuses to enable. This flag is a second, independent lock on
    # data leaving the machine.
    inference_cloud_egress_permitted: bool = False
    model_health_ttl_seconds: float = Field(default=60.0, gt=0, le=3600)
    context_token_budget: int = Field(default=2048, ge=256, le=32768)
    # Levels 3 and 4 are future-phase capabilities and are excluded by this
    # Literal, so they cannot be activated by configuration at all.
    autonomy_level: Literal["0_advisory", "1_assisted_execution", "2_controlled_autonomy"] = "0_advisory"
    plan_max_steps: int = Field(default=24, ge=1, le=64)
    mission_max_concurrent_tasks: int = Field(default=2, ge=1, le=8)

    # ---- P-03 Opportunity Discovery Engine ----
    # Discovery, research, evidence, analysis, scoring and validation are
    # deterministic and work with no source reachable at all: an opportunity that
    # obtains no evidence is reported as insufficient, not guessed at. These
    # settings govern acquisition, not whether the engine functions.
    opportunities_enabled: bool = True
    # Network egress for research is DENY BY DEFAULT and the list starts empty.
    # Every host must be named explicitly, and NetworkPolicy refuses a host that is
    # not on it - including a parent domain when only a subdomain is listed. An
    # empty list therefore means no source can be reached, which the engine reports
    # as a refusal per source rather than working around.
    research_permitted_hosts: str = ""
    research_max_sources_per_sweep: int = Field(default=10, ge=1, le=50)
    research_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    # Retrieved content is untrusted input (§27), so its size is bounded before it
    # is parsed and nothing retrieved is ever executed.
    research_max_response_bytes: int = Field(default=1_000_000, ge=1_000, le=20_000_000)
    research_max_evidence_per_sweep: int = Field(default=200, ge=1, le=5_000)
    # The level an opportunity must reach before it may be RECOMMENDED. Level 3 is
    # commercial evidence. Levels 4 and 5 require money to have actually changed
    # hands, which §26 forbids this phase from arranging, so 5 is unreachable here
    # by design rather than by configuration.
    opportunity_minimum_validation_level: int = Field(default=3, ge=0, le=5)
    opportunity_max_open: int = Field(default=50, ge=1, le=1_000)
    # Evidence older than this is marked stale and stops counting towards coverage.
    evidence_stale_after_days: int = Field(default=180, ge=1, le=3_650)

    # ---- P-04 Dynamic Agent Factory ----
    # An agent is a configuration, not a process: creating one starts no model and
    # opens no socket, and every agent shares the single ModelRouter from P-02.
    # The limits below bound the registry anyway, because an unbounded number of
    # logical agents eventually means unbounded concurrent work against a shared
    # inference semaphore on a 16 GB, four-core machine.
    agents_enabled: bool = True
    # Ceiling on live (non-retired) agents. Reaching it queues a non-essential
    # creation request rather than rejecting it outright.
    agent_max_total: int = Field(default=12, ge=1, le=64)
    # Ceiling per template, so one template cannot occupy the whole registry.
    agent_max_per_template: int = Field(default=4, ge=1, le=32)
    # Ceiling on creation requests held in QUEUE. A full queue rejects, because
    # queuing without bound is just refusing slowly and without telling anyone.
    agent_max_creation_queue: int = Field(default=20, ge=1, le=200)
    # How deep parent_agent_id chains may go. 0 means no agent may have a parent.
    agent_max_delegation_depth: int = Field(default=2, ge=0, le=4)

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("P-01 backend must bind to loopback; remote access is not implemented")
        return v

    @field_validator("ollama_base_url")
    @classmethod
    def validate_inference_endpoint(cls, v: str) -> str:
        """The inference endpoint must be loopback.

        Prompts can carry owner objectives and financial limits. An inference URL
        pointing off the machine would send them to a third party without any
        data-sharing decision having been made, so this is refused at startup
        rather than warned about at runtime.
        """
        import re as _re
        match = _re.match(r"^https?://([^:/?#]+)(?::(\d+))?", v.strip())
        if not match:
            raise ValueError("ollama_base_url must be an absolute http(s) URL")
        host = match.group(1).strip("[]").lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "inference endpoint must bind to loopback; sending prompts to a "
                "remote host requires an approved data-sharing decision"
            )
        if match.group(0).lower().startswith("https://") is False and host != "localhost":
            pass  # plain http on loopback is expected for a local model server
        return v.strip()

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
    def research_host_allowlist(self) -> tuple[str, ...]:
        """The research egress allowlist, parsed from a comma-separated string.

        Kept as a string in the environment because a JSON list in a .env file is
        easy to get subtly wrong, and an allowlist that fails to parse must fail
        closed rather than open.
        """
        return tuple(h.strip().lower() for h in self.research_permitted_hosts.split(",") if h.strip())

    @field_validator("database_url", "database_url_direct")
    @classmethod
    def _database_url_must_be_postgres(cls, value: str | None) -> str | None:
        """Fail at construction, not at first query.

        A silently ignored database URL would leave the application writing to
        SQLite while the operator believes it is writing to Postgres, which is
        the worst of both worlds. So an unparsable or unsupported value is a
        startup error.
        """
        if value is None or value == "":
            return None
        scheme = value.split("://", 1)[0].split("+", 1)[0].lower()
        if "://" not in value or scheme not in {"postgresql", "postgres"}:
            raise ValueError(
                "database_url must be a postgresql:// connection string; got "
                f"{value.split('://', 1)[0]!r}. Leave it unset to keep SQLite."
            )
        return value

    @model_validator(mode="after")
    def _direct_url_requires_a_runtime_url(self) -> "Settings":
        if self.database_url_direct and not self.database_url:
            raise ValueError(
                "database_url_direct only overrides the URL used for "
                "migrations; set database_url as well, or neither."
            )
        return self

    @property
    def database_is_sqlite(self) -> bool:
        return not bool(self.database_url)

    @staticmethod
    def _normalise_postgres(url: str, *, driver: str) -> str:
        rest = url.split("://", 1)[1]
        return f"postgresql+{driver}://{rest}"

    @property
    def migration_database_url(self) -> str:
        """The URL Alembic should use: the direct connection when one is set.

        Runtime traffic wants the pooler; DDL does not. Keeping them separate
        means a hosted deployment can pool its queries without pooling its
        migrations.
        """
        if self.database_url_direct:
            return self._normalise_postgres(self.database_url_direct, driver="psycopg")
        return self.sync_database_url

    @property
    def database_path(self) -> Path:
        return self.data_dir / "autonomus.db"

    @property
    def async_database_url(self) -> str:
        if not self.database_is_sqlite:
            return self._normalise_postgres(self.database_url, driver="psycopg")
        return f"sqlite+aiosqlite:///{self.database_path}"

    @property
    def sync_database_url(self) -> str:
        if not self.database_is_sqlite:
            return self._normalise_postgres(self.database_url, driver="psycopg")
        return f"sqlite:///{self.database_path}"


def get_settings() -> Settings:
    return Settings()
