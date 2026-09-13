# 08 — Backend and API Plan

## Components

- API gateway/auth middleware; PostgreSQL + pgvector; S3-compatible original store; async queue/workers; model runtime; audit/event store.
- Modular services: `source-registry`, `ingestion`, `processing`, `search`, `answer`, `citation`, `policy`, `admin`.
- Start as a modular monolith with isolated worker processes; split only when measured scale demands it.

## Core API contract

`POST /v1/chat` accepts `{message, language?, collection_ids?, session_id?}` and returns `{answer, status: answered|abstained|needs_review, citations[], limitations[], trace_id}`. Citations contain only ACL-approved source metadata.

`GET /v1/documents/{id}/versions/{id}/pages/{n}` streams the original only after authorisation. `POST /v1/ingestions` is admin/records-officer only; `GET /v1/search` returns evidence, not model-generated answers. `POST /v1/feedback` records correction signals separately from source truth.

Use JSON Schema/OpenAPI, pagination, idempotency keys for writes, async job IDs, per-user/tenant rate limits, structured error codes and trace IDs. Never expose raw model tool calls, internal prompts, secrets, or unauthorised result counts.

## Acceptance criteria

- Every answer can be reconstructed from request hash, index/version identifiers, prompt/version, model revision and citations without logging sensitive text unnecessarily.
- 401/403 responses reveal no document existence; load tests enforce rate limits and timeouts.
- Ingestion failures are retry-safe and do not publish partial index data.
