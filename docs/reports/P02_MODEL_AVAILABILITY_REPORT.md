# P-02 Model Availability and Hardware Report

- **Phase:** P-02
- **Date:** 2026-11-03
- **Purpose:** Record what local inference was possible on the development host, so that no P-02 claim about models rests on an assumption nobody checked.

## 1. Conclusion

**No local model could be run, and none was run.** No measurement of latency, memory or token throughput was taken at any point in P-02, and no such figure appears in any P-02 document. The engine was therefore built and verified to be fully functional with zero models installed, degrading to an explicit `ModelUnavailableError` rather than fabricating reasoning ([ADR-0017](../decisions/ADR-0017-DETERMINISTIC-FIRST-INTELLIGENCE.md)).

## 2. Inference runtimes probed

All six were probed by execution, not by assumption:

| Runtime | Present |
|---|---|
| `ollama` | **Absent** |
| `llama-server` / `llama.cpp` | **Absent** |
| `docker` | **Absent** |
| `nvidia-smi` | **Absent** |
| `pwsh` / `powershell` | **Absent** |
| `cargo` / `rustc` | **Absent** |

## 3. Network reachability

| Host | Result |
|---|---|
| `ollama.com` | **UNREACHABLE** — model weights cannot be downloaded |
| `huggingface.co` | **UNREACHABLE** — GGUF weights cannot be downloaded |
| `google.com` | **UNREACHABLE** |
| `pypi.org` | Reachable |
| `registry.npmjs.org` | Reachable (HTTP 200) |
| `api.github.com` | Reachable |

The sandbox permits outbound access only to a fixed allowlist of package and code hosts. Model distribution hosts are not on it.

## 4. Hardware

| Resource | Value |
|---|---|
| CPU | Intel Xeon @ 2.60 GHz, **2 logical cores** |
| Instruction sets | aes, avx, avx2, fma |
| GPU | **NONE** |
| `MemTotal` | ~3.85 GiB |
| `SwapTotal` | **0** |
| Free disk | ~20 GiB |
| Kernel | `6.1.158+` x86_64 |
| Python | 3.11.2 |

A 3.85 GiB ceiling with no swap is below what a useful instruct model needs alongside a running database, an event bus and a task queue. `probe_host_resources()` reports `gpu_available=False`; **no GPU detection is claimed**, because there is no GPU to detect and no code path was written to infer one.

## 5. Consequences for acceptance

Two acceptance items cannot be verified on this host and are reported as such rather than passed:

| Acceptance item | Status |
|---|---|
| "Local model integration works" | **NOT VERIFIED** |
| "Local model performance" | **NOT VERIFIED — no measurement exists** |

`OllamaProvider` is implemented against the documented Ollama HTTP API and is exercised in tests only through mock providers. Whether it works against a real server is **untested**. It is written to be provider-independent behind the `ModelProvider` protocol, so replacing or adding an adapter does not touch the router.

## 6. What would be needed to verify

On a host with a local runtime:

1. Install Ollama and pull a small instruct model (1–3 B parameters).
2. Set `model_provider=ollama` and `registered_model_id` to the pulled model id.
3. Confirm `AUTONOMUS_OLLAMA_BASE_URL` remains loopback; a non-loopback value is rejected at startup by `validate_inference_endpoint`.
4. Start the backend and call `GET /api/v1/intelligence/models` — the model should appear with `healthy` reflecting a real probe.
5. Call `POST /api/v1/intelligence/chat` with a simple question and confirm a real generated answer rather than `status=unavailable`.
6. Read `model_usage` for the recorded attempt, and confirm `estimated_cost` is `0.0` for local inference.

Only steps 5 and 6 produce measurements. Until they are run on real hardware, any latency or memory figure quoted for this system would be invented.

## 7. What was NOT attempted

- No `pip install llama-cpp-python` and no GGUF download. Both would fail on the network and would consume disk the host does not have to spare.
- No simulated model output was substituted for a real one anywhere in `backend/app/`.
- No performance figure was estimated, extrapolated or carried over from published benchmarks for other hardware.
