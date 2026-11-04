# P-00 AI Hardware Feasibility — Current Workspace Re-Audit

**Date:** 2026-11-03 (re-audit)
**Supersedes for this workspace:** sections 1 and 3 of [AI_HARDWARE_FEASIBILITY.md](AI_HARDWARE_FEASIBILITY.md), which measured ~1.94 GiB total / ~1.46 GiB available RAM
**Status:** Sandbox re-measured. **Verified local inference capacity remains zero.** Windows feasibility still pending. No benchmark performed.
**Evidence:** [P00_REAUDIT_ENVIRONMENT_EVIDENCE.json](P00_REAUDIT_ENVIRONMENT_EVIDENCE.json)

The sizing method, KV-cache reasoning and Windows envelope table in the original
report are **unchanged and still authoritative**. Only the sandbox measurements
and the conclusions that depend on them are restated here.

## 1. Re-measured envelope

| Resource | Original audit | Now | Change |
|---|---|---|---|
| Total RAM | ~1.94 GiB | **~3.85 GiB** | ~2x |
| Available RAM | ~1.46 GiB | **~3.60 GiB** | ~2.5x |
| Swap | 0 KiB | **0 KiB** | Unchanged — exhaustion is fatal, not slow |
| Logical CPUs | 2 | 2 | Unchanged |
| CPU model | not established | **Intel Xeon @ 2.60 GHz** | Newly established |
| SIMD | not captured | **aes, avx, avx2, fma present** | Newly established |
| GPU | none exposed | none exposed | Unchanged |
| Ollama | absent | **absent** | Unchanged |

## 2. The binding constraint is no longer memory — it is network

This is the material change in conclusion since the original report.

`ollama.com` and `huggingface.co` are both **unreachable** from this workspace
(verified by probe; see the environment re-audit §5). Therefore:

- No inference runtime can be installed.
- No GGUF weights can be downloaded.
- **Verified inference capacity is zero models**, exactly as before — but now for
  a reason that additional RAM cannot fix.

Doubling available memory improved *headroom*. It did not improve
*verifiability*. Any claim that local AI is "feasible here" would be unsupported,
so none is made.

One useful nuance for planning: the **`ollama` PyPI client (0.6.3, MIT,
`requires_python >=3.8`) is installable** from the reachable registry. It is a
client library, not a server or a model. That means P-02 can implement and test
the provider adapter, router, availability detection and fallback logic against a
**deterministic stub provider** without any real model — but the result must be
reported as stub-verified, never as inference-verified.

## 3. What the re-measured headroom would support, if a runtime existed

Applying the original report's method (`weight_GB ≈ params_B × effective_bits / 8`,
Q4 planned at ~4.5–5.5 effective bits per weight, plus runtime buffers, KV cache,
OS and application):

| Dense model class | Q4 weights | Verdict at ~3.6 GiB available, 0 swap, 2 cores |
|---|---:|---|
| 0.5–1B | 0.3–0.7 GB | **Plausible** — the only class with genuine headroom here |
| 2–3B | 1.1–2.1 GB | **Marginal** — could be resident, but leaves little for KV cache with no swap; OOM-killer risk and poor latency |
| 7–8B | 3.9–5.5 GB | **Not feasible** — exceeds total RAM before any runtime overhead |
| 13B+ | 7.3 GB+ | Not feasible |

Local **embedding** models in the small classes are plausible on the same
reasoning. These are planning estimates, not measurements: no tokens/second,
cold-start, quality or concurrency figure is claimed, because nothing was run.

The presence of **AVX2 and FMA** is a positive indicator for `llama.cpp`-class
CPU inference and was not recorded in the original audit. It is not a substitute
for a benchmark.

## 4. Concurrency and sharing

- 2 logical CPUs supports **one** concurrent CPU inference stream realistically.
  Parallel requests would contend for the same two cores.
- The design consequence is unchanged and now better evidenced: **one shared model
  server behind a provider adapter, with all agents queued through it.** Per-agent
  model processes are not viable at 3.85 GiB total, and Constitution §12.2 already
  forbids assuming one heavyweight process per agent.
- `AUTONOMUS_TASK_MAX_CONCURRENCY` (default 2, verified in the running backend) is
  **task** concurrency and must not be mistaken for model concurrency. When a real
  model exists, model concurrency needs its own bound.
- With **0 KiB swap**, memory exhaustion kills processes rather than degrading
  them. The existing `SystemMonitor` admission control
  (`AUTONOMUS_MEMORY_PERCENT_MAX=90`) is therefore the primary protection, and the
  original report's warning still stands: Python-level queue limits are not an
  OS-level memory sandbox.

## 5. Cloud fallback is not available as a workaround here

Cloud inference is blocked twice over: the network allowlist excludes provider
endpoints, and `AUTONOMUS_CLOUD_AI_ENABLED=true` is **rejected at startup** by
configuration validation (verified). Constitution §2.1 keeps cloud optional and
replaceable; it is not a substitute for the missing local capability in this
workspace.

## 6. Recommendation

1. **Keep `D-06` as pending.** Do not select or download a model on the strength
   of this re-audit. The gate is unchanged: hardware audit first, then one small
   approved model and a bounded benchmark.
2. **Do not treat ~3.6 GiB as an invitation to test a 3B model here.** Even if a
   runtime could be obtained, 0 swap and 2 cores make an OOM-kill likely, and the
   result would not generalise to the owner's PC.
3. **Unblock P-02 with a stub provider.** Approve implementing the model interface,
   router and availability detection against a deterministic fake provider, tested
   in CI, with real inference explicitly marked unverified. This is the only way
   intelligence work can proceed honestly from this workspace.
4. **Re-run this audit on the owner's Windows PC** (`scripts/audit_windows.ps1`)
   before any model decision. That machine's RAM, GPU, VRAM and driver support
   decide the real envelope, not this sandbox.
5. **Update `L-03`** in the risk register: its "~1.94 GiB total sandbox RAM" figure
   is stale for this workspace, though its conclusion (defer heavyweight inference)
   is unchanged.
