# Atopsy implementation audit — 2026-11-03

Source inspection before implementation. Backend and frontend are separate Git repositories; both were clean. No root Git repository or AGENTS.md was found.

| Capability | Baseline status | Evidence / integration gap |
|---|---|---|
| Authentication | Partially implemented | Node signup/login/rotation/session services exist; FastAPI reads `sub` as int although Node signs `userId` UUID. Pipeline routes do not require authentication. |
| Case management | Partially implemented | Prisma CRUD exists; list/detail/update lack case membership checks. Priority is integer, UI sends text. |
| Acquisition | Partially implemented | Real storage/checksums/metadata/audit engine. Global checksum uniqueness blocks independent case copies; upload is separate from Node evidence records. |
| OCR | Implemented but not integrated | Local Tesseract pipeline and page/word models exist, but ingestion only extracts metadata previews. |
| Extraction | Partially implemented | ExtractionEnvelope and regex spans exist; DB failures fall back to mock records. Optional commercial enrichment runs implicitly. |
| Structuring | Partially implemented | Canonical graph, normalization and provenance exist; DB errors swallowed. |
| Normalization | Partially implemented | Reuses Layer 4 if present, otherwise re-extracts independently. Universal toxicology thresholds need disabling. |
| Correlation | Implemented but not integrated | Typed multi-document engine; fuzzy identity and lexical contradiction rules require conservative handling. |
| Temporal | Implemented but not integrated | Interval/event/conflict engine exists; public timeline service is unrelated to these persisted outputs. |
| TOD | Implemented but not integrated | Candidate/signal engine exists; experimental, unvalidated approximation. Must retain alternatives and qualified review boundary. |
| Anomalies | Implemented but not integrated | Layer 8 consumes Layers 4–7; no case orchestration or finding review lifecycle. |
| Frontend | Partially implemented | Real case CRUD clients mixed with hardcoded dashboard findings, placeholder routes, socket client without server, incompatible endpoints. |
| Persistence | Broken | Prisma current UUID schema differs from only committed migration (legacy integer tables). SQLAlchemy partially maps shared tables. No run/stage history. Alembic directory has no migration files. |
| Testing | Partially implemented | Layer 5–8 scripts use synthetic entity inputs; ingestion script calls an unauthenticated running service. Several test files empty. No isolated complete workflow tests. |

Inspected: both package manifests, AI requirements, Prisma schema and migration, SQLAlchemy models/repository, all eight engine entry points and schemas, OCR/document handlers, auth dependencies/middleware, Node controllers/routes, frontend services/router/auth/layout/cases/dashboard, and existing test scripts.

Baseline validation: Node TypeScript build passes. Frontend typecheck fails (signup naming, profile, JSX, missing icon, Vite environment types). Docker daemon unavailable; local PostgreSQL binaries are installed. No existing database has been changed.

## Execution order

1. Add persistent case run/stage tracking around existing engines. Explicit dependencies, failure/skipped status, immutable snapshots, retry, incremental document reuse, provenance, schema version and deterministic idempotency.
2. Align Node-session authentication and case access. Keep Prisma as authority for shared account/case tables; additive SQL migrations only. Disable legacy unauthenticated routes in the integrated application.
3. Wire real case workspace, uploads, extraction, graph/timeline/anomalies/TOD, version history and live dashboard; remove mock navigation from the active application.
4. Add immutable review revisions, hypothesis evidence matrix, case-grounded extractive assistant and downloadable report.
5. Exercise synthetic multi-document ingestion, engine output, persistence, source grounding, authorization, incremental reuse, failures/retries and UI builds. Report measured limitations separately from execution success.

The canonical source is Layer 4's ForensicEntityGraph. Layer 2 consumes that exact graph for its enriched normalization record; it must not extract another entity set in the integrated workflow. Layer 5 onward consume the same graph.

Existing databases require inspection before migration deployment. Legacy integer tables will be retained; no reset, drop, conversion or deployment is authorized by this implementation.
