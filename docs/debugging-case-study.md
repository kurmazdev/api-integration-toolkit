# Case study: a cursor that never advances

## Symptom

An orders integration completes its first page, then repeatedly requests page 2. A naïve implementation keeps writing duplicate orders indefinitely. A timestamp watermark advanced after each page can make this worse: a later attempt may skip records that were never imported.

This repository includes a reproducible broken upstream, rather than a UI-only simulated error. Run the separate demo API, select **Repeated cursor**, and run a full synchronization. The actual HTTP response for page 2 contains valid order data but invalid continuation metadata.

## Evidence

With the baseline dataset, `limit=5`:

```text
GET /orders?limit=5&cursor=0&scenario=pagination
200 → items ORD-0001…ORD-0005, next_cursor="5"

GET /orders?limit=5&cursor=5&scenario=pagination
200 → items ORD-0006…ORD-0010, next_cursor="5"
```

The execution history reports `pagination: The API repeated its current cursor.` The run fails with **1 committed page and 5 stored records**. Its checkpoint remains `"5"`; the successful incremental watermark remains null. The second page is rejected before a database transaction starts.

## Root cause

The API's faulty branch returns the inbound cursor as the outbound continuation:

```python
# Broken: repeats the requested position.
if scenario == "pagination" and start >= limit:
    next_cursor = cursor
```

A client that stops only when `next_cursor is None` never terminates. Unique IDs alone prevent duplicate rows but do not prevent an unbounded loop, repeated requests, rate-limit exhaustion or a falsely advanced watermark.

## Correction and defensive fix

The healthy upstream computes the next position and terminates explicitly:

```python
next_start = start + limit
more = next_start < len(source)
next_cursor = str(next_start) if more else None
```

The connector compares current and next cursors before committing. The synchronization layer also stores a fingerprint of each normalized page, catching upstreams that generate changing cursor strings while returning identical records. Empty pages with a continuation and runs exceeding their configured page limit fail safely as well.

Page transactions contain both the records and the next cursor. The global watermark changes only in the final page's transaction. This makes a failed page retryable without skipping its data.

## Recovery

Select **Fix demo & resume**. This changes the demo's actual response behavior to healthy and requests the persisted cursor `"5"` again. Page 2 now returns `next_cursor="10"`; the run finishes after five committed pages with **23 unique orders**. The earlier error remains visible alongside the successful recovery events. No reset or record deletion is involved.

For a custom integration, correct the upstream or connector, then **Resume run**. If the source's cursor expired or its ordering changed, start a new full replay instead.

## Regression tests

Run:

```sh
.venv/bin/pytest -q backend/tests/test_integration.py -k bad_pages
.venv/bin/pytest -q backend/tests/test_http_boundaries.py -k changing_cursor
npm --prefix frontend run test:e2e -- --grep 'broken cursor'
```

The HTTP integration regression checks:

1. A real HTTP page 1 commits.
2. The malformed continuation from page 2 fails with `pagination` and no retries.
3. Exactly five records remain and the watermark is unchanged.
4. Resuming against the corrected HTTP API finishes the same run.
5. The database has 23 unique records and the watermark commits only on completion.

A second real HTTP origin returns the same normalized page with a different cursor on every request. Its test verifies that the fingerprint guard stops after one committed page. The browser test verifies that the diagnosis and recovery controls are usable through the interface.

The separate process-recovery regression also kills Uvicorn after page 1, restarts it against the same SQLite file, verifies `interrupted` state, then resumes to the same final record and export counts. This tests durable checkpoints beyond cooperative cancellation.
