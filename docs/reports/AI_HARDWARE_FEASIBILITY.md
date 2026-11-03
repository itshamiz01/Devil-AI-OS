# P-00 AI Hardware Feasibility Report

**Date:** 2026-11-03  
**Status:** Sandbox assessed; Windows feasibility pending; no inference benchmark performed  
**Decision:** Shared inference, bounded concurrency and local-first routing are architecturally feasible. Actual model capacity on the owner's PC is not yet established.

## 1. Evidence and limits

The available Linux workspace exposes 2 logical CPUs, approximately 1.94 GiB total RAM and 1.46 GiB available at capture, with no swap and no exposed GPU device. Ollama is not installed. See [ENVIRONMENT_EVIDENCE.json](ENVIRONMENT_EVIDENCE.json).

These are not the owner's Windows specifications. No tokens/second, model quality, cold-start time or Windows GPU compatibility claim is made.

Ollama supports native Windows operation, but its current documentation specifies Windows 10 22H2 or newer and additional driver requirements for NVIDIA/AMD acceleration. Its installation alone requires at least 4 GB of storage, before models. [2](https://docs.ollama.com/windows)

## 2. Model sizing method

A lower-bound estimate for weight storage is:

`weight_GB ≈ parameter_count_billions × effective_bits_per_weight / 8`

GGUF quantization includes metadata and non-uniform tensor precision. For rough Q4 planning, allow about 4.5–5.5 effective bits per weight, then add runtime buffers, KV cache, embeddings, the OS and the application. These are planning estimates, not model-specific measurements.

| Dense model class | Approximate Q4 weight storage | Additional considerations |
|---|---:|---|
| 0.5–1B | 0.3–0.7 GB | Small classification/extraction candidate; still needs runtime headroom |
| 2–3B | 1.1–2.1 GB | Basic instruction/tool-call candidate; quality must be tested |
| 7–8B | 3.9–5.5 GB | More capable candidate; not a comfortable sandbox workload |
| 13–14B | 7.3–9.7 GB | Requires substantially more RAM/VRAM and context headroom |
| 27–32B | 15–22 GB | Workstation-class candidate; no claim for this workspace |
| 70B | 39–48 GB | Deferred; not justified by current evidence |

KV cache depends on architecture, context, precision, group-query attention and concurrent sequences. A simplified upper planning expression is:

`KV_bytes ≈ 2 × layers × KV_heads × head_dimension × context_tokens × bytes_per_element × parallel_sequences`

Use the actual model metadata rather than treating this estimate as a guarantee. Long context and parallel requests can exhaust memory even when model weights fit. Ollama documents that parallel processing increases context-related memory allocation and exposes controls for loaded models, parallel requests and queue length. [3](https://docs.ollama.com/faq)

Mixture-of-experts models may activate fewer parameters per token, but their resident weights still require memory. Active parameter count is not total memory requirement.

## 3. Feasibility by environment

### Available sandbox

- Documentation, schema design and deterministic Python checks: feasible.
- Local embeddings: potentially feasible with a carefully selected small model, but not installed or benchmarked.
- 0.5–1B Q4 generation: a possible experiment only after approval; available memory leaves little headroom.
- 3B and larger generation: not a responsible default for this sandbox.
- Multiple resident LLMs: not recommended.
- Current verified inference capacity: **zero models**, because no inference runtime/model is installed.

### Owner's Windows PC

Cannot yet classify accurately. After the Windows audit:

| Hardware envelope | Candidate starting point, not a guarantee |
|---|---|
| 8 GB RAM, no usable GPU | Small 1–3B quantized model; short context; expect latency and quality limits |
| 16 GB RAM, CPU-only | 3B first; 7B Q4 only if measured headroom and latency are acceptable |
| 16–32 GB RAM, 8 GB VRAM | 3–8B Q4 candidate; reserve VRAM for context and desktop use |
| 32 GB RAM, 12–16 GB VRAM | 7–14B Q4 candidate, subject to architecture and benchmark |
| 64 GB RAM, 24 GB VRAM | Larger models may fit; still benchmark before selecting a default |

Do not purchase or upgrade hardware based solely on this table. CPU generation, memory bandwidth, GPU backend, thermal limits and model architecture materially affect results.

## 4. Recommended model profiles

These are capability categories, not downloaded or approved models:

| Profile | Candidate size | Purpose | Validation required |
|---|---:|---|---|
| Router/classifier | 0.5–3B | Classification, routing, simple extraction | Schema accuracy and abstention |
| General instruct | 3–8B | Planning assistance, research summarization | Grounding, instruction following, bounded tool proposals |
| Coding | 3–14B | Code suggestions and repairs | Compile/tests/security review; never self-approve deployment |
| Strong reasoning | Hardware-dependent | Difficult business analysis | Evidence quality, calibration and cost/latency |
| Embedding | Small local embedding model | Semantic retrieval | Retrieval relevance, language coverage, memory and latency |
| Speech | Deferred | Optional transcription/TTS | Separate hardware and consent assessment |

Start with **Q4_K_M or an equivalent model-supported 4-bit quantization** where available. Compare Q5/Q6 only if memory permits and quality measurements justify it. Do not assume every model offers the same quantization names. Check each model's license, provenance, context support and tool-calling behavior before adoption.

A small model is not automatically reliable enough to be the Master Intelligence. Deterministic schemas, constrained action proposals and independent result checks are required regardless of model size.

## 5. Inference architecture

```text
Agent task proposals
        ↓
Persistent, bounded task queue
        ↓
Capability/privacy/budget-aware model router
        ↓
Application-level concurrency limiter
        ↓
Shared local inference adapter (Ollama or replaceable provider)
        ↓
Structured output validation + evidence/result recording
```

- Agents are logical identities and permission scopes, not separate heavyweight model processes.
- Use one shared local model server initially.
- Start with one loaded generation model and one inference slot; benchmark before increasing either.
- Keep a separate small embedding profile only if measurements justify it.
- Bound queue length, context, output tokens, retries, wall-clock time and per-task spend.
- Apply backpressure rather than spawning more agents to clear a backlog.
- Record model/version/quantization, latency, resource observations and validation outcomes.
- Provider fallback must obey privacy and spending policy. A local failure must not silently send data to a paid cloud service.
- Explicitly disable Ollama cloud features for local-only deployments; the application must also enforce its own provider allowlist. Ollama documents `OLLAMA_NO_CLOUD=1` / `disable_ollama_cloud` for this purpose. [3](https://docs.ollama.com/faq)

## 6. Resource exhaustion behavior

1. Admit work only when queue and resource budgets permit.
2. Prefer smaller approved profiles or defer optional work.
3. Pause/reschedule noncritical agents when memory pressure rises.
4. Reject new inference cleanly when capacity is unavailable; keep essential monitoring and owner controls responsive.
5. Never retry an external side effect merely because an inference call timed out.
6. After restart, inspect durable task and tool-execution state before resuming.
7. Optional cloud offload requires explicit owner policy, data classification and budget; otherwise remain local or paused.

The OS process supervisor and resource enforcement design must be validated on Windows. Python queue limits alone are not an OS-level memory sandbox.

## 7. Benchmark gate before model selection

After explicit approval for a runtime/model download, run a versioned benchmark on the target PC:

- Cold load and warm-request latency.
- Time to first token and generation throughput.
- Peak RSS/VRAM at agreed context lengths.
- One versus two concurrent requests; measure rather than assume improvement.
- Structured-output validity and tool-proposal correctness on a fixed test set.
- Grounded-summary and refusal/abstention behavior.
- Embedding retrieval quality and resource use.
- Queue saturation, cancellation, out-of-memory handling and restart recovery.
- UI responsiveness while inference is active.

Record hardware, driver, runtime, model digest, quantization, prompt set and configuration. Define acceptable latency and quality thresholds before testing. No benchmark result is fabricated in P-00.

## 8. Conclusion

**Local AI feasibility: partially assessed, not verified on the target.** The architecture can share inference across many logical agents, but the current sandbox cannot substantiate a production local-model claim. Windows hardware results, model approval and measured benchmarks remain prerequisites for an informed default model selection.
