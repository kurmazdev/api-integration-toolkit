# API Integration & Debugging Toolkit

A Python and React workbench for synchronizing a REST orders API into SQLite, diagnosing HTTP and pagination failures, and resuming interrupted runs from durable checkpoints. The bundled demo uses a separate HTTP server and synthetic order data.

## Features

- Configure dotted field mappings, bearer/API-key authentication, and cursor, page, or offset pagination.
- Preview and validate records before committing data.
- Retry transient HTTP failures with backoff and Retry-After support.
- Persist each validated page and its checkpoint atomically.
- Resume failed, cancelled, or interrupted runs; replay safely with idempotent upserts.
- Inspect run history and actionable diagnostics; export CSV or Excel.

## Technologies

Python 3.11+, FastAPI, HTTPX, SQLite, openpyxl, React 19, TypeScript, Vite, pytest, and Playwright.

## Installation

Requires Python 3.11+ and Node.js 20.19+ (Node 22 recommended). Tests also use OpenSSL. Use a compatible interpreter for `python3` below. Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c requirements.lock.txt -e '.[test]'
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python scripts/run.py
```

Open http://127.0.0.1:8000. The launcher starts the application and separate demo API on ports 8000/8001, both on loopback. It refuses occupied ports. Ctrl+C stops both. Use `.venv/bin/python scripts/run.py --dev` for Vite on port 5173.

## Usage

1. Select the Orders API demo and **Test & preview** to validate the first page without writing records.
2. Select **Run sync** to import 23 unique baseline orders across five pages.
3. Use **Replay all** to demonstrate unchanged records without duplication.
4. Select a failure scenario, such as repeated cursors, malformed responses, HTTP 429/500, timeouts, or interrupted processing.
5. Inspect events, correct the failure, and resume from the committed checkpoint.
6. Export committed records as CSV or XLSX.

For a custom integration, select a public HTTPS endpoint and configure the field paths, pagination envelope, and session credential. The connector uses a fixed five-field order schema; other authentication flows or schemas require an adapter.

## Reliability and security

- A page is fully validated before records, counters, and continuation commit in one SQLite transaction. Only a completed run advances the incremental watermark.
- Stable IDs make storage idempotent. Requests may repeat after interruption; this is at-least-once fetching, not exactly-once delivery.
- Repeated cursors, page fingerprints, empty continuing pages, and run limits stop invalid pagination.
- Credentials remain in process memory and must be re-entered after restart; they are not stored in SQLite, browser storage, exports, or diagnostics.
- Custom destinations require public HTTPS on port 443. DNS answers are validated, the vetted IP is pinned, and original Host/TLS SNI preserve certificate verification. Redirects, URL credentials, and environment proxies are blocked.
- Local Host/Origin checks, a mutation header, bounded inputs/responses, safe validation errors, and restrictive response headers protect the local boundary.
- Spreadsheet exports neutralize formula prefixes. SQL values use bound parameters.

SQLite state is stored in ignored `.runtime/toolkit.db`. `TOOLKIT_DB` overrides its path. `DEMO_URL` is an operator setting for the trusted demo origin, never an editable private-URL allowlist.

This is a single-user local application. Run one backend worker per database and keep it on loopback. It does not provide accounts, distributed synchronization, OAuth refresh, source deletions, bidirectional sync, or source snapshot isolation. Resetting the workspace deletes its stored records and history; export first.

## Verification

```sh
.venv/bin/python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
# Stop the manually running toolkit first; browser tests use an isolated database:
CI=1 npm --prefix frontend run test:e2e
```

The backend suite exercises real HTTP/TLS origins, export safety, pagination failures, and process interruption/recovery. Browser tests cover synchronization, replay, failure diagnosis, resume, downloads, reset confirmation, and mobile layout. Test output and traces are ignored.

## Command-line synchronization

With the server running and credentials configured:

```sh
.venv/bin/python scripts/sync_once.py
.venv/bin/python scripts/sync_once.py --full --export .runtime/orders.csv
```

The command exits successfully only when synchronization completes. Overlapping runs are rejected; credentials do not survive a backend restart.

## Structure

- `backend/toolkit/`: API boundary, connector, validation, synchronization, storage, demo API.
- `backend/tests/`: unit, HTTP/TLS, export, and process-recovery regressions.
- `frontend/src/`: configuration, synchronization controls, records, and diagnostic views.
- `frontend/e2e/`: browser workflows.
- `scripts/`: local launcher and one-shot synchronization.
- `docs/`: architecture and a reproducible pagination debugging case study.

Dependencies retain their respective licenses. No third-party dependency source is vendored in this repository.
