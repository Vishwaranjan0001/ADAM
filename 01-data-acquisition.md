# 01 — Data Acquisition and Ingestion

## Objective and boundary

Create an authorised, repeatable inventory of **public or department-approved** Uttarakhand records. Do not bulk-scrape portals merely because they are publicly reachable; agree collection permissions, crawl rate and owner with each department.

## Initial sources and acquisition playbook

| Priority | Official source | Acquisition action | Provenance condition |
|---|---|---|---|
| P0 | [Treasury/IFMS GOs](https://ekosh.uk.gov.in/government-orders/) | Owner-approved sitemap/list crawler; capture listed PDF and detail page | URL, title, displayed date, download time and SHA-256 |
| P0 | [Treasury RTI manuals](https://ekosh.uk.gov.in/document-category/rti-documents-manuals/) | Seed rules/manuals index | retain category and original file |
| P0 | [Rural Development documents](https://ukrd.uk.gov.in/documents/) | Paginate only approved categories | owner and departmental scope |
| P1 | [Audit GOs](https://uttarakhandaudit.uk.gov.in/document-category/government-orders/) and [Board of Revenue documents](https://bor.uk.gov.in/documents/) | Department-specific connectors | source URL and fetch log |
| P1 | [Uttarakhand OGD](https://uttarakhand.data.gov.in/) | Use portal export/API where supplied; retain metadata | GODL-India metadata/license record |
| P1 | official Gazette/Act pages supplied by owning department | Add only after legal-owner confirmation | publication/gazette number and effective date |
| P2 | internal departmental records | signed upload via authorised records officer | classification, retention and access ACL |

Do not treat search-engine results, copies, blogs, or unofficial uploads as authority. Court material and central legislation can be linked as external references, but are outside this Uttarakhand repository unless separately authorised.

## Connector procedure

1. Obtain a source onboarding sheet: departmental owner, written authority, permitted paths, access classification, refresh cadence, terms, retention, and contact.
2. Discover index/list pages; enqueue only allowed links and allow-listed government domains. Respect robots, terms and server rate limits.
3. Download immutable original bytes to object storage; calculate SHA-256; store HTTP headers/status and UTC retrieval time.
4. Create a `document_version` even if a URL already exists. Detect byte hashes; never overwrite the prior version.
5. Run malware/type checks, OCR/parse workflow, quality review, then publish only approved versions to the index.
6. Schedule weekly delta discovery (or owner-selected cadence); quarantine removals and notify the owner rather than deleting evidence.

## Core schema

`documents(id, department_id, doc_type, title, language, authority_level, classification, current_version_id, lifecycle_status)`

`document_versions(id, document_id, source_url, source_locator, issued_on, published_on, effective_from, effective_to, go_number, gazette_number, supersedes_version_id, sha256, mime_type, byte_size, retrieved_at, provenance_status, license_id, original_object_key)`

`ingestion_runs(id, source_id, started_at, completed_at, collector_version, count_found, count_downloaded, failures_json)` and `access_grants(subject_id, document_id|classification, action, expires_at)`.

Use controlled vocabularies for document type, department, status and classification; preserve unknown fields rather than inventing values.

## Acceptance criteria

- A pilot source produces a signed inventory with 100% original URLs, hashes and fetch timestamps.
- Re-running a connector is idempotent and does not duplicate byte-identical files.
- A source owner can see, approve, pause and remove a connector without deleting audit history.
- No document becomes searchable before malware/type validation and provenance status is `verified` or visibly `unverified`.

## Dependencies

Object storage, PostgreSQL, departmental approvals, source registry and the processing queue in module 02.
