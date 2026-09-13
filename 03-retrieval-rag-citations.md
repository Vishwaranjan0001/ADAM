# 03 — Retrieval, RAG and Citations

## Retrieval design

Create chunks by semantic structure (order/section/paragraph), retaining `version_id`, page range, section heading, language, dates, authority, department, classification and review status. Aim for 350–700 tokens with 10–15% overlap; never split an operative clause from its proviso or schedule.

1. Query understanding extracts filters only when explicit (department, date, GO number, document type).
2. Hybrid retrieve: PostgreSQL full-text/BM25 + local vector search (pgvector) over authorised chunks.
3. Apply metadata ACLs before ranking; rerank top results with a compact cross-encoder only if benchmarks justify it.
4. Build an evidence packet from 3–8 highest-quality passages, including conflicting/amending records.
5. Generator may use only that packet. A citation validator checks that every material claim maps to one or more passages.

## Citation contract

Each answer citation exposes `document title`, department, GO/gazette number if known, version/hash, issue date, page, section, source URL, retrieval timestamp and a link to the original PDF page. A citation is a source pointer, not a claim of legal validity.

For amendments/repeals, show a **currency banner**: “Applicable status not conclusively determined” unless the corpus has an approved relationship and effective-date record. Never infer supersession from similar language alone.

## Hallucination controls

- No evidence → answer: “I could not establish this from the approved repository,” followed by search suggestions.
- Require direct citations for dates, money, rule numbers, authorities, obligations, exceptions and legal conclusions.
- Do not answer from model memory; retrieved public evidence is mandatory even for common facts.
- Quote minimally, paraphrase clearly, label conflicts, and offer the original document.
- High-risk prompts (legal advice, sanction approval, eligibility, disciplinary action) produce a research brief with “human authority required,” never a definitive determination.

## Evaluation and acceptance

Build a gold set of ≥200 Hindi/English officer questions, including known-answer, no-answer, amendments, conflicting documents and ACL-denied cases. Pilot gate: ≥90% recall@10 for answer-bearing queries; ≥95% citation page precision; 100% tested no-answer cases refuse unsupported claims; 0 cross-tenant/ACL leaks. Measure by department and language.

## Dependencies

Approved chunks (02), ACL/index store (07/08), model service (04).
