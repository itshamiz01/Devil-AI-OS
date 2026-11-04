# Model Routing and Provider Abstraction (P-02 §6)

## 1. Provider independence

`ModelProvider` is a Protocol with four methods — `generate`, `check_health`, `list_models`, `get_capabilities` — plus a `name` attribute. Nothing in the intelligence package imports an Ollama-specific type or calls an Ollama-specific endpoint directly; `OllamaProvider` is one adapter behind that protocol, and the router only ever sees the protocol.

| Adapter | Status |
|---|---|
| `NoRuntimeProvider` | **Implemented**; the default when `model_provider="none"` |
| `OllamaProvider` | **Implemented against the documented HTTP API; NOT VERIFIED** against a live server |
| Cloud providers (OpenAI, Anthropic, others) | **Not supported**; routing logic exists and is tested, but no adapter is registered and the phase flag forbids it |

`OllamaProvider` never downloads weights. Registering a model points at a server the owner must already be running; if the model id is not present locally, health probing reports it unavailable.

## 2. Registry

`ModelRegistry` holds `ModelRecord` entries: provider, local/cloud, declared `ModelCapabilities` (context window, structured output, tool calling, reasoning, minimum RAM), availability, cost per 1k tokens, limitations and a `configuration` dict. Duplicate registration raises unless `replace=True` is passed explicitly.

Declared capabilities are **configuration, not measurement**. A local GGUF model served by Ollama can return JSON, but whether it does so reliably depends on the specific weights, so `supports_structured_output=True` records a claim the owner makes. Every registered record carries that limitation string.

The `configuration` dict is where a base URL or API key would live. `GET /api/v1/intelligence/models` deliberately omits it (§14: never expose model credentials or unrestricted provider configuration). A test asserts the provider port never appears in the response body.

## 3. Selection

`ModelRouter.generate` filters the registry against `RouteRequirements` and `InferencePolicy` **before** attempting anything. Filters applied: capability requirements, local-first preference, cost ceiling, cloud permission, data-egress permission for sensitive requests, context-window fit, and memory admission.

Ordering is deterministic: local before cloud, then smaller declared footprint before larger. Ties break on model id, so the same input always selects the same model.

Because unpermitted providers are removed at selection rather than placed at the end of a fallback chain, there is no ordering in which a paid provider can be reached by accident. See [ADR-0016](../decisions/ADR-0016-NO-PAID-INFERENCE-FALLBACK.md).

## 4. Fallback

Fallback is bounded and explicit. On `ModelTimeoutError` or `ModelOutputError` the router tries the next **permitted** candidate. On `ModelUnavailableError` it does the same. When no permitted candidate remains it raises, carrying the list of models actually tried.

`asyncio.CancelledError` is never caught, so a cancellation propagates instead of being converted into a fallback attempt.

If no viable model exists at all, the router short-circuits before any adapter is called — no health probe, no connection attempt, no latency.

## 5. Concurrency, timeouts and admission (§6.5)

| Control | Setting | Default |
|---|---|---|
| Simultaneous generations | `inference_max_concurrent` | 1 (1–8) |
| Per-generation timeout | `inference_timeout_seconds` | 60 (>0, ≤600) |
| RAM the inference may commit | `inference_ram_safety_fraction` | 0.8 (>0, ≤1) |
| Cost ceiling | `inference_max_cost_per_1k_tokens` | 0.0 (0–100) |
| Health cache lifetime | `model_health_ttl_seconds` | 60 (>0, ≤3600) |
| Declared model RAM need | `registered_model_min_ram_gb` | 1.0 (0–64) |

Memory admission compares the model's declared `min_ram_gb` against `available_ram_gb * ram_safety_fraction`, read from a `resource_probe` callable. `factory.probe_host_resources` implements it with `psutil` using `interval=None`, so it never blocks on a sampling window. A GPU relaxes the RAM requirement when present; `gpu_available` is reported `False` on the P-02 host and no GPU detection is claimed.

Health results are cached for `model_health_ttl_seconds`. A model with no registered adapter is rejected **before** its health is consulted, because such a model can never probe healthy and reporting "unhealthy" would hide the actionable cause.

`engine.py` calls `probe_health()` lazily immediately before each `generate`, never at construction. Startup cannot block on an absent model server (§18).

## 6. Usage accounting

Every attempt produces a `UsageRecord`: request id, provider, model, local flag, duration, prompt/completion tokens, estimated cost, success, error, purpose and correlation id. Local inference is recorded at cost `0.0`.

Records are appended to `model_usage` through the router's `usage_listener`, which `factory` wires to `IntelligenceRepository.record_usage`. The router treats a listener failure as non-fatal: an accounting problem can never abort a generation.

`model_usage` is **operational accounting, not a financial ledger**. It is never summed into business revenue or expenses (§17).

Token counts are estimates where the provider does not report them: `estimate_tokens` divides characters by `CHARS_PER_TOKEN_ESTIMATE = 4.0`. This is documented as an estimate wherever it is surfaced.

## 7. Endpoint validation

`Settings.validate_inference_endpoint` refuses any `ollama_base_url` whose host is not loopback (`127.0.0.1`, `localhost`, `::1`). Verified refusals: `http://10.0.0.5:11434`, `http://api.openai.com`. Verified acceptances: `http://127.0.0.1:11434`, `http://localhost:11434`. The engine therefore cannot be pointed at an external inference service by editing configuration alone.

## 8. Verification status

| Claim | Evidence |
|---|---|
| Selection, ordering, fallback, admission, cancellation, accounting | `tests/test_model_router.py` — 35 tests, all passing |
| No automatic paid fallback | Asserted on the exact list of models tried (`["local-small"]`) |
| Sensitive data never routed to cloud without egress permission | Dedicated test |
| Bounded concurrency equals 1 | Asserted on the provider's observed maximum concurrency |
| `OllamaProvider` against a real server | **NOT VERIFIED** — no runtime installed, `ollama.com` unreachable |
| Latency, memory, token throughput of any real model | **NOT MEASURED** — no figure may be quoted |
