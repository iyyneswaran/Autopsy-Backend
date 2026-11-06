# ATOPSY local workflow

This checkout keeps the existing React/Vite frontend, Express/Prisma application server and FastAPI/SQLAlchemy forensic engines. The integrated public route is `/api/v1/intelligence`, proxied through authenticated Express sessions. FastAPI validates the same JWT **and the live database session**. Legacy unauthenticated pipeline endpoints are no longer mounted; their source code remains available.

## Existing synthetic environment on this computer

The separate cluster lives in `../.local-test/pgdata`, listens on loopback port **15432**, and uses database `atopsy_synthetic` / user `atopsy_test`. It contains synthetic fixtures only. Existing application `.env` files and user databases were not modified. Local files are in `../.local-test/evidence` and test files in `../.test-artifacts/evidence`.

From this backend folder, start the database, then keep these services running in separate PowerShell terminals:

```powershell
./scripts/local-synthetic.ps1 Database
./scripts/local-synthetic.ps1 Node
./scripts/local-synthetic.ps1 AI
./scripts/local-synthetic.ps1 Frontend
```

Open <http://localhost:3000>. The local synthetic browser-validation account is:

- Email: `synthetic.17f3fb0252054366b8fc76c451e18b2a@example.test`
- Password: `SyntheticPass123!`
- These credentials and launcher secrets are deliberately test-only. Do not use this configuration for real evidence or expose the services publicly.

The launcher assumes dependencies and builds are present. If services were already running, do not start duplicate instances on the same ports. Stop an individual foreground service with Ctrl+C. Stop this cluster with `pg_ctl -D ../.local-test/pgdata stop`; this retains its data.

Tesseract 5.5.3 was installed under the current user's `AppData/Local/AtopsyTools/Tesseract`. The launcher sets `TESSERACT_CMD` explicitly. A different installation can be supplied with `-Tesseract`. No paid OCR or language-model API is used by the integrated path.

## Fresh setup

Use the repository's locked Node dependencies and AI `requirements.txt`. This implementation was exercised with Python 3.11, PostgreSQL 18 and the locally installed Node runtime.

```powershell
# backend/server
npm ci
npx prisma generate
npm run build
# frontend
npm ci
npm run lint
npm run build
# backend/ai
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt
```

Install the free local Tesseract executable and English language data from the [official Tesseract distribution guidance](https://tesseract-ocr.github.io/tessdoc/Downloads). Set `TESSERACT_CMD` to the executable path. Native UTF-8 text and native-text PDFs do not require OCR.

Create a **new empty dedicated database**, then supply its URL through `DATABASE_URL` to both servers. In `backend/server`, run `npx prisma migrate deploy` and `npx prisma generate`. Both servers must share the same `JWT_ACCESS_SECRET` (at least 32 characters); Node also requires `JWT_REFRESH_SECRET`, `CORS_ORIGIN=http://localhost:3000` and `FASTAPI_URL=http://127.0.0.1:8001`. Set writable `STORAGE_ROOT` and `TEMP_DIR` for FastAPI. Use unique secrets outside synthetic testing. The synthetic launcher intentionally does not create a cluster or migrate any database.

## Database ownership and migration boundaries

All three migrations were applied successfully to a fresh isolated `atopsy_migration_test` database. A Prisma diff against the resulting schema was empty.

- The original integer `User`, `Case`, `Evidence`, `Analysis` tables remain intact and are represented as ignored legacy models.
- The additive UUID migration creates the shared `users`, `investigations`, `evidence`, session and other application tables already described by the existing Prisma code.
- The additive pipeline migration creates the existing AI-owned tables and new run/stage/review/hypothesis records.
- Prisma tracks the complete schema to prevent future migrations from proposing deletion of AI tables. SQLAlchemy writes AI records and maps shared fields to their actual Prisma column names. Runtime `create_all()` was removed.
- An existing database may already contain some UUID or pipeline tables without recorded migration history. Inspect and baseline it before deployment. Do **not** run reset, db push, or blindly deploy these creation migrations to such a database. No legacy IDs, passwords or evidence are converted automatically.

Existing user-database migration is deliberately pending inspection. The new synthetic database is the validated local deliverable.

## Validation

Keep PostgreSQL and Node running; stop FastAPI so its queue worker cannot race injected failures:

```powershell
./scripts/local-synthetic.ps1 Test
```

This runs the complete synthetic multi-document integration suite and updates `ai/tests/validation_metrics.json`. It creates isolated test accounts/cases and never deletes existing cases. The guard requires a test/synthetic database name. The Node server must point to that same database and use the same JWT secret.

Existing Layer 5–8 regression scripts can also be run from `backend/ai` with `PYTHONPATH=.`:

```powershell
./venv/Scripts/python.exe tests/test_layers_5_6.py
./venv/Scripts/python.exe tests/test_layers_7_8.py
```

The old unauthenticated HTTP pipeline smoke test targets retired endpoints; it is superseded by `test_integrated_workflow.py`, not counted as passing. Empty legacy test files are not validation.

## Investigator walkthrough

1. Log in, create an investigation and open its workspace.
2. Upload the six `.txt` files under `ai/tests/fixtures/investigation` together. Processing is queued durably; the workspace polls stage states. Originals are preserved under UUID storage keys.
3. Inspect extraction, canonical entities, source excerpts and verified originals. Source pages are zero-based internally and one-based in the UI/report citations.
4. Review correlation, timeline, unresolved dates, experimental TOD alternatives and anomaly leads. An exact/fuzzy match is a matching method, not investigator verification; co-document links do not establish causation.
5. Save review decisions or corrections. These append immutable revisions and preserve the original extraction. Cached unchanged entities retain earlier reviews; recomputed findings require review again.
6. Create competing hypotheses and assign observations as consistent, inconsistent, neutral or unknown. Save revisions and compare the matrix.
7. Ask the assistant for documented injuries or unreviewed observations. It returns extractive answers with source-validated excerpts; unsupported inferences return insufficient evidence.
8. Export the readable Markdown report or complete JSON report. Both identify the analysis version, sources, reviews, hypotheses and limitations. Reviews/hypotheses are current at export time and retain run/revision references; an analysis version is not a frozen later human-review history.
9. Upload supplementary evidence, compare the new analysis version and inspect audit history. Retry creates another run while reusing eligible successful document outputs. A worker interruption is recorded as a failed run with successful stages retained.

## Boundaries

This is a tested local investigation workflow, not a validated forensic diagnostic system. Rule-based extraction and local OCR need larger independently annotated, multilingual and degraded-document evaluation. The measured tiny synthetic subsets do not establish general accuracy. TOD approximations remain experimental, with alternatives and caveats retained.

Case access uses the existing owner/assignee/admin model. There is no organization/tenant model in the original schema, so cross-organization tenancy is not claimed. The assistant is deterministic retrieval; no freeform LLM or autonomous hypothesis assessment is enabled. The active UI has no fake dashboard data or unfinished navigation entries.

PDF processing is limited to 200 pages and fails explicitly beyond that limit. Handwriting quality depends on local Tesseract. Unsupported media remain originals with explicit extraction failures. Large-case performance, exhaustive browser/device coverage, production operations, dependency security remediation, and a production migration remain separate validation work.
