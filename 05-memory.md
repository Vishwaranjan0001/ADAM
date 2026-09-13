# 05 — Conversation Memory

## Design

Use minimal, explicit memory. The source corpus is institutional knowledge; chat history is not. Store a short per-session summary (query intent, selected filters, citations already opened, user corrections) with a TTL. Do not add conversational text into the retrieval index by default.

`chat_sessions(id, user_id, classification_ceiling, created_at, expires_at)`
`chat_turns(id, session_id, role, content_ciphertext, cited_chunk_ids, created_at, retention_tag)`
`session_summaries(session_id, summary_ciphertext, source_turn_ids, expires_at)`

No cross-user memory. Persistent preferences require opt-in, purpose limitation and a user-visible delete control. Classified/PII content uses the shortest approved retention; access and deletion are audited.

## Acceptance criteria

- A new session cannot retrieve a prior user’s turns.
- Summary cannot introduce facts absent from cited turns; source turn IDs are retained.
- Expiry/deletion removes encrypted content and makes it unavailable to retrieval; audit event remains without content.

## Dependencies

Identity, encryption keys and retention schedule from module 07; API from module 08.
