# 04 — Model and Agent Architecture

## Practical recommendation

Use a **single primary local text model** for the Mac pilot: Qwen3-4B Instruct/its current supported quantised build, loaded at Q4 (roughly 2.5–3.5GB model file; runtime memory varies). Qwen’s model card lists Apache-2.0 licensing and multilingual/agent capabilities. Keep a smaller fallback (Qwen3 1.7B/compatible 1–2B instruct model) for low-memory smoke tests. Do not load multiple LLMs concurrently.

Gemma 3 4B is a valuable evaluation comparator and supports Hindi, but it is gated under [Gemma terms](https://huggingface.co/google/gemma-3-4b-it) rather than Apache-2.0; legal/procurement review is required before selection. Llama-family weights likewise require their specific licence review. Model names, checksums, prompts and licences are release-controlled artefacts.

## Resource budgets

| Environment | Running profile | Disk / RAM guidance |
|---|---|---|
| 8GB MacBook Air | one Q4 1.7–4B model, 2k–4k context, single request; local embedding model; queued OCR | reserve ≥2GB macOS headroom; do not run OCR/indexing while chatting |
| Team/dev server | same model service, CPU benchmark; 8–16GB RAM preferred | model cache may be 10–20GB |
| Government production | approved GPU/CPU nodes after measured load test; independent workers | 30–40GB **disk cache** ceiling for approved models, OCR and embeddings; size RAM/VRAM from tests |

“30–40GB” is a storage budget, not evidence that an 8GB laptop can run it all. Suggested pilot cache: generator 3–4GB, embeddings <1GB, reranker <1GB, OCR assets 1–3GB, originals/index determined by corpus; cap cache and use one active heavy worker.

## Bounded orchestration

`authenticate → classify request → retrieve → evidence/currency checks → generate cited answer or abstain → validate citations → audit`.

Tools are read-only: search, open cited source, list authorised collections. No web browsing, emailing, editing records, procurement action, or database write tool is available to the model. The “agent” is a state machine with max one retrieval and one answer pass; it does not self-expand tasks.

## Model controls and acceptance

- Pin model revision, quantisation, serving runtime and prompt template; SBOM/license record required.
- Enforce temperature 0–0.2, output schema and token limit; redact system prompts and keys.
- Promotion needs module 03 gold-set results, Hindi review, latency/memory evidence and governance approval.
- The selected model must abstain correctly on all curated unanswerable/high-risk test cases.
