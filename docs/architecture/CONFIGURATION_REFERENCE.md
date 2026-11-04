# Configuration Reference (P-01 + P-02 + P-03)

Configuration is centralized in `backend/app/core/config.py` using Pydantic Settings. Environment variables use the `AUTONOMUS_` prefix. Secrets are not stored in configuration tables or logs.

| Variable | Default | Meaning |
|---|---:|---|
| `AUTONOMUS_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `AUTONOMUS_HOST` | `127.0.0.1` | Loopback only in P-01 |
| `AUTONOMUS_PORT` | `8000` | Local API port |
| `AUTONOMUS_ALLOW_REMOTE_ACCESS` | `false` | Must remain false; remote access is not implemented |
| `AUTONOMUS_DATABASE_URL` | *(empty)* | Optional `postgresql://` connection string (e.g. Supabase). Empty keeps the local SQLite database; an unsupported scheme is a startup error rather than a silent fallback |
| `AUTONOMUS_DATABASE_URL_DIRECT` | *(empty)* | Optional direct (non-pooled) `postgresql://` URL used **for migrations only**; requires `AUTONOMUS_DATABASE_URL` to be set as well. Matching is case-insensitive, so the mixed-case spelling `AUTONOMUS_DATABASE_URL_direct` binds to the same field |
| `AUTONOMUS_RUN_MIGRATIONS_ON_STARTUP` | `true` | Applies the Alembic chain during startup. Set `false` on a serverless host, where every cold start would otherwise re-run it and concurrent starts could race |
| `AUTONOMUS_DATA_DIR` | `<repo>/data` | SQLite database and runtime files |
| `AUTONOMUS_LOG_DIR` | `<repo>/logs` | Rotating JSON logs |
| `AUTONOMUS_LOG_LEVEL` | `INFO` | Log level |
| `AUTONOMUS_LOG_MAX_BYTES` | `1048576` | Size at which `autonomus.log` rotates (min 1024) |
| `AUTONOMUS_LOG_BACKUP_COUNT` | `3` | Rotated log files retained |
| `AUTONOMUS_BACKUP_DIR` | `<repo>/backups` | Verified database snapshots; restore is CLI-only (ADR-0014) |
| `AUTONOMUS_BACKUP_RETENTION_COUNT` | `7` | Newest backups kept before pruning (1-100) |
| `AUTONOMUS_TASK_QUEUE_CAPACITY` | `100` | Maximum active task records admitted |
| `AUTONOMUS_TASK_MAX_CONCURRENCY` | `2` | Worker concurrency |
| `AUTONOMUS_TASK_DEFAULT_TIMEOUT` | `30` | Default handler timeout seconds |
| `AUTONOMUS_TASK_MAX_RETRIES` | `3` | Default retry limit |
| `AUTONOMUS_SCHEDULER_POLL_INTERVAL` | `0.1` | Seconds between retry-promotion and approval-expiry sweeps |
| `AUTONOMUS_TASK_APPROVAL_TTL_SECONDS` | `3600` | Lifetime of the approval gating an `approval_required` task (60-86400). On expiry the task is cancelled by the sweep, never left waiting |
| `AUTONOMUS_RETRY_BASE_DELAY` | `0.1` | Exponential backoff base seconds |
| `AUTONOMUS_RETRY_MAX_DELAY` | `5` | Maximum retry delay seconds |
| `AUTONOMUS_SHUTDOWN_TIMEOUT` | `10` | Graceful cleanup window seconds |
| `AUTONOMUS_MEMORY_PERCENT_MAX` | `90` | Nonessential task admission threshold |
| `AUTONOMUS_DISK_PERCENT_MAX` | `90` | Nonessential task admission threshold |
| `AUTONOMUS_CPU_PERCENT_MAX` | `95` | Reported in resource snapshots and thresholds |
| `AUTONOMUS_DOCS_ENABLED` | `true` | Serves `/docs` and `/openapi.json`; disable in hardened deployments |
| `AUTONOMUS_SESSION_TTL_MINUTES` | `60` | Owner session expiry |
| `AUTONOMUS_LOGIN_RATE_LIMIT` | `5` | Login attempts per minute per client key |
| `AUTONOMUS_EXTERNAL_EXECUTION_ENABLED` | `false` | Must remain false in P-01 |
| `AUTONOMUS_FINANCIAL_EXECUTION_ENABLED` | `false` | Must remain false in P-01 |
| `AUTONOMUS_CLOUD_AI_ENABLED` | `false` | Must remain false in P-01 |

Invalid critical settings fail startup. Remote binding, remote access and phase-execution flags are rejected by validators.

## P-02 intelligence settings

Added by P-02 (Master Intelligence Engine). All sixteen are validated at configuration load; an invalid value fails startup rather than degrading silently.

| Variable | Default | Meaning |
|---|---:|---|
| `AUTONOMUS_INTELLIGENCE_ENABLED` | `true` | Master switch for the intelligence engine. When false, `/api/v1/intelligence` answers `409` rather than pretending to work |
| `AUTONOMUS_MODEL_PROVIDER` | `none` | `none` or `ollama`. With `none` no runtime is registered, so generation returns an explicit limitation instead of a fabricated answer (§6.4) |
| `AUTONOMUS_REGISTERED_MODEL_ID` | `*(empty)*` | Identifier of an **already downloaded** local model. Weights are never fetched by the application; an empty value registers no model |
| `AUTONOMUS_REGISTERED_MODEL_CONTEXT_WINDOW` | `4096` | Declared context window in tokens (512-2000000). A request exceeding it is refused or shortened, never silently truncated (§6.5) |
| `AUTONOMUS_REGISTERED_MODEL_MIN_RAM_GB` | `1.0` | RAM the model needs, in GiB (0-64). Drives memory-aware admission so inference cannot starve the Core OS (§18) |
| `AUTONOMUS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Loopback only. A non-loopback value is rejected at startup by `validate_inference_endpoint` |
| `AUTONOMUS_INFERENCE_MAX_CONCURRENT` | `1` | Simultaneous in-flight generations (1-8) |
| `AUTONOMUS_INFERENCE_TIMEOUT_SECONDS` | `60` | Per-generation timeout in seconds (>0, <=600). On timeout the router falls back to another *permitted* model or reports the limitation |
| `AUTONOMUS_INFERENCE_RAM_SAFETY_FRACTION` | `0.8` | Fraction of available RAM inference may commit (>0, <=1). The remainder is headroom reserved for the Core OS |
| `AUTONOMUS_INFERENCE_MAX_COST_PER_1K_TOKENS` | `0.0` | Cost ceiling per 1k tokens (0-100). `0.0` means local-only: no paid model can satisfy it |
| `AUTONOMUS_INFERENCE_CLOUD_EGRESS_PERMITTED` | `false` | Must remain false while `AUTONOMUS_CLOUD_AI_ENABLED` is false. Even when true, cloud routing stays inert until the owner enables that phase flag |
| `AUTONOMUS_MODEL_HEALTH_TTL_SECONDS` | `60` | How long a health probe is cached in seconds (>0, <=3600). Health is probed lazily so startup never blocks on an absent model server (§18) |
| `AUTONOMUS_CONTEXT_TOKEN_BUDGET` | `2048` | Assembled context budget in tokens (256-32768). Overflow raises `ContextOverflowError` rather than silently dropping a protected financial or security constraint (§12.3) |
| `AUTONOMUS_AUTONOMY_LEVEL` | `0_advisory` | `0_advisory`, `1_assisted_execution` or `2_controlled_autonomy`. Levels 3 and 4 are not valid values and are refused at configuration load (§15) |
| `AUTONOMUS_PLAN_MAX_STEPS` | `24` | Maximum steps in one plan (1-64). A larger plan is rejected rather than truncated |
| `AUTONOMUS_MISSION_MAX_CONCURRENT_TASKS` | `2` | Tasks one mission may have in flight (1-8), so a single mission cannot monopolise the P-01 queue (§18) |

### Inference endpoint validation

`AUTONOMUS_OLLAMA_BASE_URL` is checked by `validate_inference_endpoint` in `backend/app/core/config.py`. Only loopback hosts (`127.0.0.1`, `localhost`, `::1`) are accepted. A LAN address or a public API endpoint is **rejected at startup**, so the engine cannot be pointed at an external inference service by editing configuration alone.

### Autonomy level

`AUTONOMUS_AUTONOMY_LEVEL` sets the *initial* level only. Changing level at runtime requires the owner-only `intelligence.autonomy` permission, is audited, and publishes `AutonomyLevelChanged`. A model can never raise its own level: `AutonomyController.request_change` raises `AutonomyEscalationError` unless `authorized_by_owner` is true, and levels 3 and 4 raise it unconditionally because P-02 does not implement them (§15). The P-01 permission engine remains authoritative at every level.

### Cloud routing is implemented but inert

`ModelRouter` and `InferencePolicy` support cloud candidates and are unit-tested with `cloud_enabled=True`. In the running application that path is unreachable, because `validate_phase_flags` rejects `AUTONOMUS_CLOUD_AI_ENABLED=true`. Enabling cloud inference is an owner decision, not a code change; see `docs/decisions/ADR-0015-INTELLIGENCE-ENGINE-BOUNDARIES.md`.

### No paid fallback

If no permitted model is available the engine reports the limitation (§6.4). It never silently switches to a paid provider: `ModelRouter` excludes cloud candidates during *selection* when they are not permitted, so no fallback path can reach one. `test_model_router.py` asserts the list of models actually tried.

## P-03 opportunity discovery settings

Added by P-03 (Opportunity Discovery Engine). All nine are validated at configuration load; an invalid value fails startup rather than degrading silently.

| Setting | Default | Meaning |
| --- | --- | --- |
| `AUTONOMUS_OPPORTUNITIES_ENABLED` | `true` | Builds the P-03 subsystem at startup. When false, `Services.opportunities` is None and every `/api/v1/opportunities` route returns 409 rather than a half-built engine |
| `AUTONOMUS_RESEARCH_PERMITTED_HOSTS` | `""` | Comma-separated network egress allowlist for research acquisition. **Deny by default and empty by default**: `NetworkPolicy` refuses any host not named here, and allows a listed subdomain but never its parent. An empty value means no external source can be contacted, and every sweep returns one refusal per source instead of guessing (§27) |
| `AUTONOMUS_RESEARCH_MAX_SOURCES_PER_SWEEP` | `10` | Sources contacted in one acquisition sweep (1-50). Also used as the per-source per-minute request ceiling, so a sweep cannot exceed the rate limit a descriptor declares (§30) |
| `AUTONOMUS_RESEARCH_TIMEOUT_SECONDS` | `15.0` | Per-request acquisition timeout in seconds (>0, <=120). A timeout is recorded as a refusal with its reason, never retried silently |
| `AUTONOMUS_RESEARCH_MAX_RESPONSE_BYTES` | `1000000` | Cap on retrieved content (1000-20000000). Retrieved content is untrusted input, so it is truncated before parsing and is never executed (§27) |
| `AUTONOMUS_RESEARCH_MAX_EVIDENCE_PER_SWEEP` | `200` | Evidence records one sweep may create (1-5000). Bounds memory and database growth during a large sweep (§30) |
| `AUTONOMUS_OPPORTUNITY_MINIMUM_VALIDATION_LEVEL` | `3` | Validation level (0-5) an opportunity must reach before it may be classified RECOMMENDED. Level 3 is commercial evidence. Levels 4 and 5 require money to have actually changed hands, which §26 forbids this phase from arranging, so a setting of 5 makes recommendation unreachable by design |
| `AUTONOMUS_OPPORTUNITY_MAX_OPEN` | `50` | Open opportunities the engine will hold (1-1000). Opening beyond it returns 409 rather than growing without bound (§30) |
| `AUTONOMUS_EVIDENCE_STALE_AFTER_DAYS` | `180` | Age in days (1-3650) after which evidence is marked OUTDATED and stops counting towards evidence coverage. A stale figure is not a current one, and pricing in particular goes out of date |

### Research egress is deny by default

`AUTONOMUS_RESEARCH_PERMITTED_HOSTS` is the only path by which the engine may contact an external host, and it is empty by default. `NetworkPolicy` refuses a host that is not named, permits a listed subdomain but never its parent domain, and rejects a hostname that merely ends with a permitted suffix. An empty allowlist is therefore a valid and safe configuration: no source can be reached, and each acquisition returns a refusal naming the reason.

This matters because a refusal is a **result**. Section 19 forbids inventing statistics, prices, market sizes or publication dates, and forbids claiming a source was queried when it was not. When no host is permitted, the correct output is "insufficient verified evidence" together with the per-source refusals that explain it - not a plausible-looking market analysis.

### No setting enables spending money

There is deliberately no configuration key that permits purchasing a domain, a subscription, a dataset or advertising, placing an order, registering a business, signing a contract, collecting a payment or creating any financial obligation. Section 26 prohibits all of these at every autonomy level. A setting would imply the capability exists and is merely switched off; it does not exist, and `GovernanceGate` refuses the action outright. `AUTONOMUS_FINANCIAL_EXECUTION_ENABLED` remains refused at startup by `validate_phase_flags`, unchanged from P-01.

### Minimum validation level and what it cannot reach

`AUTONOMUS_OPPORTUNITY_MINIMUM_VALIDATION_LEVEL` gates the RECOMMENDED classification. Setting it to 4 or 5 does not make those levels attainable: level 4 requires evidence that a customer actually paid or committed a refundable deposit, and level 5 requires settled revenue. Neither can be produced by search volume, social views, likes, AI personas, hypothetical surveys, competitor existence, model-generated willingness to pay, a generated invoice, an unpaid order, an unverified screenshot, a forecast or a simulated transaction (§18). Since §26 forbids this phase from arranging a real transaction, a setting of 5 makes recommendation unreachable - which is the honest outcome, and the factory records it as a startup note rather than failing.

## Emergency stop

The owner's emergency stop is **not** an environment variable. It is durable runtime state, persisted in the `system_configurations` table so that it survives restart and can never be cleared by editing configuration or by any automatic path (ADR-0013). It is controlled only through:

```
POST /api/v1/system/emergency/activate   # permission: system.emergency (owner-only)
POST /api/v1/system/emergency/clear      # permission: system.emergency (owner-only)
GET  /api/v1/system/emergency            # permission: system.read
```

Both write operations require a non-empty `reason`, which is persisted and audited but never written to log messages.

## Not a setting: `AUTONOMUS_OPERATING_MODE`

`.env.example` still carries `AUTONOMUS_OPERATING_MODE=simulation` for historical compatibility. It is **inert**: it is not a `Settings` field and `extra="ignore"` discards it. P-01 does not implement operating modes and the four modes P-12 requires are not named in any approved document, so no semantics have been invented here. Tracked as `D-15`; the owner must decide whether to wire it or remove it.

## Coverage check

Every `Settings` field is documented above. `scripts/audit_config_docs.py` diffs `Settings.model_fields` against this file and `.env.example`, and fails on any undocumented field. Verify by hand with:

```
python -c "import sys;sys.path.insert(0,'backend');from app.core.config import Settings;print(len(Settings.model_fields))"
```

and compare against the `AUTONOMUS_*` entries in this file.
