"""An actual HTTP upstream: failures occur at the protocol and payload boundaries."""
import asyncio
from datetime import datetime, timezone
from collections import defaultdict
from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse, Response
from .models import SCENARIOS

app = FastAPI(title="Toolkit demonstration upstream")
attempts = defaultdict(int)
REVISION = 0
NAMES = ["Atlas supply", "Northstar studio", "Juniper works", "Cedar & co.", "Signal labs", "Harbor systems", "Mono studio", "Fieldnote", "Orbit design", "Pine collective", "Arc workshop", "Forma goods", "Current studio", "Mesa systems", "Bloom supply", "Copper works", "Parallel labs", "Index studio", "Oak & ash", "Thread design", "Vector goods", "Alpine studio", "Relay systems"]

def records():
    result = [{"id": f"ORD-{i + 1:04}", "name": name, "status": [" PAID ", "pending", "paid", "refunded"][i % 4],
               "amount": f"{45 + i * 17.25:.2f}", "updated_at": f"2026-10-{i + 1:02}T12:00:00Z",
               "internal_note": "Not mapped or stored"} for i, name in enumerate(NAMES)]
    if REVISION:
        result[0].update(amount="199.95", updated_at="2026-11-01T12:00:00Z")
        result.append({"id": "ORD-0024", "name": "Newleaf studio", "status": "paid", "amount": "82.50", "updated_at": "2026-11-02T12:00:00Z"})
    return result

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/revision")
def revise():
    global REVISION
    REVISION = 1
    return {"revision": REVISION, "message": "One order updated and one added."}

@app.post("/reset")
def reset():
    global REVISION
    REVISION = 0
    attempts.clear()
    return {"revision": 0}

@app.get("/orders")
async def orders(limit: int = Query(5, ge=1, le=100), cursor: str = "0", page: int = 1, offset: int = 0,
                 pagination: str = "cursor", scenario: str = "healthy", updated_since: str = "",
                 authorization: str = Header(""), x_demo_run: str = Header("preview")):
    if authorization != "Bearer local-demo-token" or scenario == "expired_auth":
        return JSONResponse({"detail": "Token expired", "secret": "never-log-upstream-bodies"}, status_code=401)
    if scenario not in SCENARIOS:
        return JSONResponse({"detail": "Unknown scenario"}, status_code=400)
    try:
        start = int(cursor) if pagination == "cursor" else ((page - 1) * limit if pagination == "page" else offset)
    except ValueError:
        return JSONResponse({"detail": "Bad cursor"}, status_code=400)
    if start < 0:
        return JSONResponse({"detail": "Bad offset"}, status_code=400)
    # Bound this demo's fault bookkeeping as well as client resource use.
    if len(attempts) > 5000:
        attempts.clear()
    key = (x_demo_run[:80], scenario, start)
    attempts[key] += 1
    attempt = attempts[key]
    if start >= limit:
        if scenario == "server_error" and attempt <= 2:
            return JSONResponse({"error": "Temporary database outage"}, status_code=500)
        if scenario == "rate_limit" and attempt == 1:
            return JSONResponse({"error": "Rate limit"}, status_code=429, headers={"Retry-After": "0.15"})
        if scenario == "malformed":
            return Response('{"items": [', media_type="application/json")
        if scenario == "timeout" and attempt == 1:
            await asyncio.sleep(3.0)
    if scenario == "slow":
        await asyncio.sleep(0.35)
    source = records()
    if updated_since:
        since = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
        # Inclusive watermark deliberately replays equal timestamps, preventing tie loss.
        source = [r for r in source if datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00")) >= since]
    if scenario == "duplicates" and source:
        source = source[:4] + [source[3]] + source[4:10] + [source[3]] + source[10:]
    rows = [dict(r) for r in source[start:start + limit]]
    if scenario == "incomplete" and start >= limit and rows:
        rows[-1].pop("updated_at")
    next_start = start + limit
    more = next_start < len(source)
    next_cursor = str(next_start) if more else None
    if scenario == "pagination" and start >= limit:
        next_cursor = cursor
    return {"items": rows, "next_cursor": next_cursor, "has_more": more, "total": len(source)}
