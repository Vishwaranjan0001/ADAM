# 11 — Testing and Integration

## Test layers

| Layer | Core checks |
|---|---|
| Unit | metadata validation, hashes, chunk boundaries, ACL predicates, citation schema |
| Contract | OpenAPI compatibility; retries/idempotency; auth/error non-disclosure |
| Corpus | parser/OCR golden PDFs, Hindi/English, tables, corrupt files, amended GOs |
| RAG | gold questions, no-answer, conflicts, dates/amounts, citation-page precision |
| Security | RBAC/ABAC, injection-in-document, XSS, upload malware/type, secrets/log review |
| UX | keyboard/screen-reader, bilingual layout, source opening, voice consent/transcript edit |
| Performance | cold/warm local model, concurrent production load, queue backpressure, recovery |

## Fixtures and measurement

Maintain a de-identified, permissioned benchmark corpus with ground-truth passages and adjudication notes. Freeze it per release; never tune exclusively on the final holdout. Track retrieval recall@k, nDCG, citation precision/coverage, OCR CER/WER, unsupported-claim rate, abstention precision, p50/p95 latency, denial-leak count and user correction rate.

## Integration acceptance

- An uploaded approved PDF travels original → reviewed text → index → cited chat answer with correct source page.
- An amendment/conflict query exposes relevant versions and avoids unsupported currency claims.
- ACL denied content is absent from search, answer, citations, logs and error text.
- Backup restore recreates originals, metadata and index aliases; audit trail remains usable.

Automate regression tests in CI; run security and human officer acceptance before each pilot release.
