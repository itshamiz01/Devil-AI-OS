# P-00 Deliverable B — AI Hardware Feasibility Report

**STATUS: VERDICT ISSUED 9 Nov 2026 — based on owner-provided target specs (via the P-04 prompt, stated as approximate): Intel Core i7-4712HQ · 16 GB RAM · NVIDIA Quadro K1100M 2 GB. Remaining unknowns: OS version, disk, installed tool versions, `ollama list` — these affect setup, not this verdict.**

## VERDICT FOR THIS MACHINE: CPU-ONLY, SMALL MODELS — PARTIALLY FEASIBLE

- **GPU is unusable for Ollama.** The Quadro K1100M is a 2013 Kepler card (GK107, CUDA compute capability **3.0**, 2 GB GDDR5, 0.54 TFLOPS — verified against published spec sources 9 Nov 2026). Ollama's NVIDIA support requires compute capability **5.0+**. There is no driver or configuration fix for this; do not plan around GPU inference on this machine.
- **CPU is the inference engine.** i7-4712HQ: Haswell, 4 cores / 8 threads, AVX2 — supports GGUF inference. Realistic tiers (estimates, to be benchmarked at P-15, never promised): **1–3B Q4** models are the interactive tier (classification, extraction, short drafting); **7–8B Q4** (~5.2 GB) fits in the 16 GB RAM alongside the OS and app but will be slow — suitable for queued/background reasoning, not interactive chat; **14B+ is not a plan** on this machine (RAM pressure + speed).
- **Embeddings: fully feasible locally** (small models, CPU).
- **Concurrency: 1 inference slot** is the sane default; P-01's bounded queue + P-02's router already assume this shape. P-04's shared-inference, no-process-per-agent design is not optional on this hardware — it is survival.
- **Strategic consequence:** the hybrid lock (ADR-001) carries real weight here. Heavy reasoning/coding tasks are exactly what optional, owner-enabled, per-business-budgeted cloud inference exists for. Local-first remains the default for privacy, cost and all routine work; the deterministic components (planning baseline, scoring, finance, permissions) need no model at all and are unaffected.
- **This verdict retroactively validates two earlier decisions:** P-02's deterministic-first planner (acceptance passes with no model) and the refusal to lock 100%-local in ADR-001.

## Sizing rules (evidence-based, November 2026 sources)

Rule of thumb for GGUF inference: **≈0.6 GB of memory per billion parameters at Q4_K_M**, plus context/KV-cache headroom. Practical VRAM tiers for Q4 models (Ollama on Windows):

| Model class | Examples | VRAM needed (Q4) | Recommended VRAM | RAM if CPU-offloaded |
|---|---|---|---|---|
| 1–3B | small/fast classifiers, qwen3:1.7b, gemma3:1b | 1–2 GB | 4 GB | 8 GB |
| 4–8B | gemma3:4b (~3.3 GB), qwen3:8b (~5.2 GB) | 3.3–5.2 GB | 8 GB | 16 GB |
| 12–14B | qwen3:14b, gemma3:12b | 8–9.3 GB | 12 GB | 32 GB |
| 27–32B | qwen3:32b | 16–20 GB | 24 GB | 32–64 GB |
| 70B+ | llama3-class 70B Q4 | ~43 GB | 48 GB | 64 GB — **not a consumer-desktop plan** |

Platform facts: Ollama requires Windows 10 22H2+; NVIDIA CUDA is the best-supported path (compute capability 5.0+, current drivers — 551.61+ per Ollama's Windows docs); AMD on Windows works via ROCm for RDNA3-class cards (RX 7600–7900 XTX) and via Vulkan more broadly, with older AMD cards at risk of CPU fallback; CPU-only runs everything but slowly (practical ceiling ≈7B at Q4 for interactive use); no NPU acceleration. If a model exceeds VRAM, Ollama splits layers between GPU and CPU — functional, slower.

Embeddings: small local embedding models (a few hundred MB) run efficiently on CPU — **local embeddings are feasible on essentially any target** and need no cloud.

## Inference architecture (decided, independent of the final verdict)

- **One shared Ollama server for all agents.** No per-agent model instances (Constitution §12.2).
- Model Router (P-02) selects per task class: small/fast model for classification/extraction · mid model (7–14B class, hardware permitting) for research, content and planning support · coding-capable model for development tasks · deterministic code (never an LLM) for all financial maths, authorisation and risk limits.
- **Bounded concurrency:** a queue with a small number of simultaneous inference slots (starting assumption: 1–2 on consumer hardware, tuned at P-15 benchmarks); agents wait in the persistent task queue rather than contending for memory.
- **Resource exhaustion behaviour:** when RAM/VRAM pressure is detected, the scheduler defers low-priority inference, shrinks context, or routes an explicitly cloud-enabled task to the optional cloud path — it never swaps the machine into failure or kills business processes silently.
- Cloud fallback is for **capability gaps** (a task class the local tier demonstrably fails), not a default — each cloud call is costed into the owning business's ledger.

## What the verdict will look like once hardware is known

| If the machine has… | Local tier verdict |
|---|---|
| No usable GPU, 16 GB RAM | 3–8B Q4 on CPU only — slow; research/planning quality limited; cloud fallback becomes important (owner decision); defer media-heavy work |
| 8 GB VRAM GPU, 16–32 GB RAM | 7–8B fully on GPU, 14B with offload — a workable Horizon 1 machine |
| 12–16 GB VRAM, 32 GB RAM | 14B on GPU, 32B with offload — comfortable for all P-02 task classes |
| 24 GB+ VRAM | 32B on GPU — headroom for concurrency experiments at P-15 |

**Do not promise performance the hardware cannot deliver (P-00 §6). This report promises nothing until the audit lands.**
