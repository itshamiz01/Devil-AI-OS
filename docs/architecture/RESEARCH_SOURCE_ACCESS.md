# Research Source Access (P-03)

Covers `backend/app/opportunities/sources.py` — §12, and the research workflow in `research.py` — §22 and §24.

## 1. The governing constraint

**No live market source is reachable from this build environment.** The probe that established this is at [`docs/reports/P03_SOURCE_ACCESS_PROBE.txt`](../reports/P03_SOURCE_ACCESS_PROBE.txt). Two findings shaped the design:

* A **TCP-connect probe gives a false positive here.** A transparent proxy completes the handshake and then drops the TLS negotiation, so 28 of 29 hosts reported "reachable" at the socket level. Only an HTTPS-GET probe tells the truth: **2 of 16 research URLs were usable**, and neither is a market source.
* Every host that *is* permitted is a package registry or GitHub. There is no search engine, marketplace, forum, trend service, government statistics site or vendor pricing page available.

The design response is not to stub the network layer. It is to build the real thing and configure it to **deny all egress by default**, so that the absence of sources is a configuration fact the owner can change, not a code fact hiding behind a mock.

## 2. `SourceDescriptor`

A source is declared, not discovered. Fifteen fields; four are required:

| Field | Required | Notes |
|---|---|---|
| `source_id` | yes | Identity |
| `name` | yes | Human label |
| `source_type` | yes | One of 11 `SourceType` values |
| `access_method` | yes | One of 7 `AcquisitionMethod` values |
| `licensing` | **yes** | Free text. **A source with no declared licence cannot be registered at all** |
| `requires_auth` | no, `False` | |
| `auth_mechanism` | no, `'none'` | `Literal['none', 'api_key', 'oauth2', 'owner_session']` |
| `rate_limit_per_minute` | no | |
| `returned_fields` | no, `()` | What the source actually returns |
| `refresh_frequency` | no, `'manual'` | `Literal['realtime', 'daily', 'weekly', 'monthly', 'manual']` |
| `reliability` | no, **`untrusted`** | The default is the pessimistic one |
| `supported_operations` | no, `()` | Empty means nothing may be requested |
| `status` | no, **`not_configured`** | The default is the pessimistic one |
| `endpoint_template` | no | |
| `notes` | no | |

Three defaults encode a bias: a new source is **untrusted**, **not configured**, and supports **no operations**. Each of those must be explicitly overridden before the source can contribute anything.

`licensing` being required is the most consequential choice here. The system may not use a source whose terms it has not been told.

The eleven source types: `search_engine`, `marketplace`, `community_forum`, `review_site`, `trend_service`, `government_statistics`, `vendor_pricing`, `news`, `registry`, `owner_supplied`, `mock`.

The seven acquisition methods: `http_get`, `official_api`, `authenticated_api`, `structured_feed`, `owner_upload`, `mock_adapter`, `unavailable`.

## 3. `NetworkPolicy`

| Field | Default | Effect |
|---|---|---|
| `permitted_hosts` | `frozenset()` | **Empty means deny all** |
| `allow_any_https` | `False` | The escape hatch; off by default |
| `request_timeout_seconds` | `15.0` | |
| `max_response_chars` | `200000` | Hard cap on what enters the process |
| `max_requests_per_minute_per_source` | `10` | |
| `user_agent` | `AUTONOMUS-P03/1.0 (research; owner-authorized)` | Identifies itself honestly |
| `follow_redirects` | `False` | **A redirect cannot move a request to an unpermitted host** |

`host_permitted(url)` is the single gate every request passes through:

```python
if self.allow_any_https:            return True
if scheme not in {"http", "https"}: return False
host = (parsed.hostname or "").lower().rstrip(".")
if not host:                        return False
if host in self.permitted_hosts:    return True
return any(host.endswith(f".{allowed}") for allowed in self.permitted_hosts)
```

The subdomain rule is one-directional and the direction matters: permitting `example.com` also permits `api.example.com`, but permitting `api.example.com` does **not** permit `example.com`. Widening downward is safe because the registrable host was already vouched for; widening upward would let one narrow grant cover an entire domain.

`follow_redirects=False` closes the obvious bypass. With redirects enabled, a permitted host could 302 to an unpermitted one and the policy would have approved the first hop only.

## 4. Adapters

| Adapter | Purpose |
|---|---|
| `SourceAdapter` | The interface all adapters satisfy |
| `HttpSourceAdapter` | `(descriptor, policy, *, transport=None, credentials=None)`. Real HTTP, gated by the policy. `transport` is injectable so tests never touch a network |
| `MockSourceAdapter` | Returns fixture content, labelled as such |
| `UnreachableSourceAdapter` | Always refuses. Used for sources that exist in the catalog but cannot be reached |

**Credentials live only in the adapter, never in the descriptor.** `HttpSourceAdapter` takes `credentials` as a constructor argument; `SourceDescriptor` has no credential field at all, and neither does the `research_sources` table. A credential cannot be persisted, serialised into a snapshot, or logged, because there is nowhere in the data model to put it.

## 5. `SourceRegistry`

| Method | Behaviour |
|---|---|
| `register(descriptor, adapter=None)` | Add a source. Registration **does not** place its host on the allowlist |
| `get(source_id)` | Raises `SourceNotFoundError` if absent |
| `adapter(source_id)` | Resolve the adapter |
| `list_sources()` / `by_type(...)` | Reads |
| `set_status(...)` | Move a source's `SourceStatus` |
| `authorized_operations(source_id)` | `()` unless status is `authorized`; otherwise the descriptor's `supported_operations` |
| `fetch(source_id, operation, params=None)` | **Raises** on an unknown source |
| `fetch_many(source_ids, operation, params=None)` | Returns `dict[str, FetchResult]`. **One bad source cannot destroy the batch** |

`fetch` and `fetch_many` differ deliberately in failure mode. A single `fetch` of an unknown id is a programming error and raises. `fetch_many` is a bulk operation over sources that may individually be misconfigured, so it returns a per-source result and lets the caller see which ones refused and why. A collection-returning method that let one bad element abort the whole result would hide eleven good refusals behind one exception.

`authorized_operations` returning `()` for any status other than `authorized` means registration alone grants nothing. The six statuses are `authorized`, `not_configured`, `unreachable`, `rate_limited`, `forbidden_by_policy`, `degraded`.

`snapshot()` returns `allow_any_https`, `authorized`, `by_status`, `permitted_hosts`, `registered` and `sources` — where `sources` is a list of dicts carrying `source_id`, `name`, `type`, `status`, `access_method`, `operations`, `reliability`, `licensing`. **No credential material appears in the snapshot**, because none exists in the model.

## 6. The refusal taxonomy

`FetchResult` carries either `content` or a `refusal` — never both, never neither.

`SourceRefusal` fields: `source_id`, `operation`, `url`, `category`, `detail`, `http_status`, `retryable`, `attempted_at`.

Twelve `RefusalCategory` values: `not_configured`, `not_authorized`, `host_not_permitted`, `network_unreachable`, `timeout`, `rate_limited`, `authentication_failed`, `policy_forbidden`, `invalid_request`, `unsupported_operation`, `response_too_large`, `malformed_response`.

`retryable` distinguishes a transient condition (`timeout`, `rate_limited`, `network_unreachable`) from a permanent one (`host_not_permitted`, `not_configured`, `policy_forbidden`). The task manager uses this: retrying a policy refusal would burn attempts on an outcome that is already correct.

`summarise_refusals(...)` collapses refusals into the counts and reasons the report renders. **A refusal is a finding.** In this environment, where no source is reachable, refusals *are* the research output — the honest statement that the system tried and could not obtain evidence.

## 7. The default catalog is empty

`default_source_catalog()` returns `()`. This is intentional and is the single most important configuration fact about P-03:

* With no sources registered, `research_permitted_hosts` defaults to `""` → deny all.
* Every acquisition attempt therefore produces a `host_not_permitted` or `not_configured` refusal.
* Zero evidence flows in, so `OpportunityScorer` returns `INSUFFICIENT_EVIDENCE`, `recommendable=False`, `attractiveness == 0`, `scorable_count == 0`, TAM and SOM `None`, and validation level 0.
* The report still renders all nine sections, each saying what could not be determined.

Nothing is fabricated to fill the gap. Recorded in [ADR-0018](../decisions/ADR-0018-NO-INVENTED-MARKET-DATA.md).

Registering a source succeeds and is useful — it records the descriptor, its licence and its supported operations — but the API response states explicitly that **registration does not place the host on the allowlist**. Those are two separate owner decisions: *what is this source* and *may we contact it*.

## 8. The research workflow

`research.py` defines a 13-stage workflow: `intake`, `initial_screening`, `source_selection`, `acquisition`, `evidence_extraction`, `market_analysis`, `competitor_analysis`, `business_model_analysis`, `commercial_analysis`, `risk_review`, `scoring`, `validation`, `reporting`.

`WorkflowReport` carries `opportunity_id`, `started_at`, `finished_at`, `completed`, `halt_reason`, `halted_at`, `stages`, `total_evidence`, `total_refusals`. Each `StageResult` carries `stage`, `executed`, `started_at`, `finished_at`, `skipped_reason`, `items_produced`, `evidence_ids`, `refusals`, `data_gaps`, `summary`.

A stage that is **skipped says why**. A halted workflow names the stage it stopped at — for a prohibited candidate that is `initial_screening`, and no acquisition stage runs at all.

`total_refusals` is reported alongside `total_evidence` in every workflow report, so a run that gathered nothing is visibly a run that gathered nothing.

## 9. `ResearchScheduler` — caller-timed only

`ResearchScheduler.snapshot()` reports `autonomous_scheduling: False`, and this is not a temporary state. §24 defers autonomous scheduling to **P-12**. In P-03 the scheduler:

* builds a `ResearchTaskSpec` for a named stage,
* selects sources for a sweep,
* and submits to the P-01 `TaskManager` **only when the owner asks**.

`ResearchTaskSpec`: `opportunity_id`, `stage` (a `Literal` of the six research stages: `source_sweep`, `market_sizing`, `competitor_scan`, `cost_verification`, `demand_verification`, `compliance_scan`), `source_ids`, `query`, `parameters` (required dict), `max_items=25`, `timeout_seconds=30.0`, `priority=5`, `created_at`.

* `spec.handler()` returns `"research.sweep"` for **all six stages** — one handler, with the stage carried in the payload.
* `spec.task_name()` returns `f"research.{stage}:{opportunity_id}"[:200]`.
* `enqueue(spec, *, principal_id)` uses idempotency key `f"{opportunity_id}:{stage}"[:128]` and returns a record with `opportunity_id`, `stage`, `task_name`, `handler`, `source_ids`, `principal_id`, `dispatched`, `task_id`, `reason`.

**It never presents an undispatched task as queued.** `dispatched` is a real boolean and `reason` explains a `False`.

The `POST /{id}/enqueue-research` endpoint is an owner-requested immediate submission. It schedules nothing, and its response says so with `autonomous_scheduling: false`.
