import asyncio
import csv
import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from .connector import RestConnector
from .models import Config, IntegrationError, RunInput, SaveConfig, SCENARIOS
from .storage import Store
from .sync import SyncService


def create_app(db_path=None, demo_url=None):
    store = Store(db_path or os.getenv("TOOLKIT_DB", ".runtime/toolkit.db"))
    service = SyncService(store, demo_url or os.getenv("DEMO_URL", "http://127.0.0.1:8001"))

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        await service.stop()
        service.credential = None

    app = FastAPI(title="API Integration & Debugging Toolkit", lifespan=lifespan)
    app.state.store, app.state.service = store, service

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # Single-user local application. No CORS; guard against cross-site localhost writes.
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("localhost", "127.0.0.1", "testserver"):
            return JSONResponse({"message": "Untrusted Host header"}, status_code=400)
        origin = request.headers.get("origin")
        if origin and origin not in ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"):
            return JSONResponse({"message": "Cross-origin request blocked"}, status_code=403)
        if request.method in ("POST", "PUT", "DELETE") and request.headers.get("x-toolkit-request") != "1":
            return JSONResponse({"message": "Missing local request header"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"message": "Invalid content length"}, status_code=400)
        if length > 20000:
            return JSONResponse({"message": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(IntegrationError)
    async def integration_error(request, error):
        return JSONResponse({"code": error.code, "message": error.message, "hint": error.hint}, status_code=409 if error.code in ("busy", "resume", "history_limit") else 422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Pydantic's default response echoes input, which could include credentials.
        return JSONResponse({"code": "validation", "message": "Invalid settings.", "hint": "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())[:1000]}, status_code=422)

    @app.get("/api/settings")
    def settings():
        row = store.config()
        return {"config": json.loads(row["config"]), "watermark": row["watermark"], "has_credential": bool(service.credential), "scenarios": SCENARIOS}

    @app.put("/api/settings")
    async def save(payload: SaveConfig):
        if service.busy():
            raise IntegrationError("busy", "Stop the active run before editing settings.", "The run uses a frozen configuration.")
        if payload.credential is not None and any(ord(c) < 32 or ord(c) > 126 for c in payload.credential):
            raise IntegrationError("credentials", "Credential contains invalid characters.", "Paste a single token without line breaks.")
        if payload.config.source == "custom":
            from .security import public_destination
            await public_destination(payload.config.url)
        if service.busy():
            raise IntegrationError("busy", "A run started while settings were being validated.", "Stop the run before changing settings.")
        current = Config.model_validate_json(store.config()["config"])
        with store.db() as db:
            if current != payload.config and db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]:
                raise IntegrationError("configuration", "Reset the workspace before changing the saved integration.", "Export existing records first. Credentials can be refreshed without changing settings.")
            db.execute("UPDATE settings SET config=? WHERE id=1", (payload.config.model_dump_json(),))
        if (current.source, current.url, current.auth) != (payload.config.source, payload.config.url, payload.config.auth):
            service.credential = None
        if payload.credential is not None:
            service.credential = payload.credential or None
        return {"saved": True, "has_credential": bool(service.credential)}

    @app.post("/api/preview")
    async def preview(payload: RunInput):
        c = Config.model_validate_json(store.config()["config"])
        page = await RestConnector(c, service.credential, service.demo_url, payload.scenario, uuid.uuid4().hex).fetch()
        return {"items": page.records, "has_more": page.next_token is not None, "message": "Connection verified; first page validated and normalized. Nothing written."}

    @app.post("/api/runs", status_code=202)
    async def start(payload: RunInput):
        return {"id": service.start(payload.scenario, payload.full)}

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume(run_id: str, payload: RunInput):
        return {"id": service.start(payload.scenario, resume_id=run_id)}

    @app.post("/api/runs/{run_id}/stop")
    async def stop(run_id: str):
        if service.active_id != run_id or not service.busy():
            raise HTTPException(409, "Run is not active")
        await service.stop()
        return {"stopped": True}

    @app.get("/api/runs")
    def runs():
        with store.db() as db:
            return [dict(r) for r in db.execute("SELECT id,status,started,ended,scenario,pages,seen,inserted,updated,unchanged,retries,error,since FROM runs ORDER BY rowid DESC LIMIT 100")]

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        result = store.run(run_id)
        if not result:
            raise HTTPException(404, "Run not found")
        return result

    @app.get("/api/records")
    def records(limit: int = 25, offset: int = 0):
        if limit < 1 or limit > 100 or offset < 0 or offset > 50000:
            raise HTTPException(422, "Invalid record window")
        return store.records(limit, offset)

    @app.get("/api/export/{format}")
    def export(format: str):
        if format not in ("csv", "xlsx"):
            raise HTTPException(404, "Choose csv or xlsx")
        fields = ["id", "name", "status", "amount", "updated_at"]
        rows = store.records(50000)["items"]
        # Neutralize spreadsheet formulas in every text cell, including whitespace-prefixed formulas.
        def safe(value):
            return "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
        if format == "csv":
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(fields)
            writer.writerows([[safe(row[f]) for f in fields] for row in rows])
            content, media = buffer.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
        else:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Orders"
            sheet.append(fields)
            for row in rows:
                sheet.append([safe(row[f]) for f in fields])
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for col, width in zip("ABCDE", [20, 30, 18, 15, 32]):
                sheet.column_dimensions[col].width = width
            buffer = io.BytesIO()
            workbook.save(buffer)
            content, media = buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="orders.{format}"'})

    @app.post("/api/reset")
    async def reset():
        if service.busy():
            raise IntegrationError("busy", "Stop the active run before resetting.", "Committed records will be removed by reset.")
        with store.db() as db:
            for table in ("records", "events", "fingerprints", "runs"):
                db.execute(f"DELETE FROM {table}")
            db.execute("UPDATE settings SET watermark=NULL WHERE id=1")
        return {"reset": True}

    @app.post("/api/demo/revision")
    async def revision():
        if service.busy():
            raise IntegrationError("busy", "Wait for the run to finish before changing demo data.", "The demo keeps source data stable within a run.")
        import httpx
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
                response = await client.post(service.demo_url + "/revision")
                response.raise_for_status()
        except httpx.HTTPError:
            raise IntegrationError("demo_unavailable", "The demo API is unavailable.", "Start the separate demo API on port 8001.")
        return {"message": "Demo source updated: one changed order and one new order. Run incrementally to fetch them."}

    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
