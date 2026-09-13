# 10 — Deployment and Local Development

## MacBook Air (8GB) developer profile

Use public pilot PDFs only. Run one service profile at a time: database + API + UI **or** OCR worker **or** local model. Limit model context to 2k–4k tokens, one concurrent generation and small document batches. Prefer Apple-native/CPU-supported inference runtime only after measuring actual memory and latency; stop background indexing while testing chat. Version/download large artefacts outside the repository and cap the local cache.

Suggested compose profiles: `core` (PostgreSQL/API/UI), `inference` (one Q4 generator), `ocr` (one worker), `eval` (offline benchmark). A fresh developer can bootstrap with an anonymised mini corpus and seeded evaluation set, never a production backup.
