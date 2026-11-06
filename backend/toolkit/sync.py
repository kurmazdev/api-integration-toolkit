import asyncio
import json
import uuid
from .connector import RestConnector
from .models import Config, IntegrationError
from .storage import now

class SyncService:
    def __init__(self, store, demo_url, connector_factory=RestConnector):
        self.store, self.demo_url = store, demo_url
        self.connector_factory = connector_factory
        self.credential = None
        self.task = None
        self.active_id = None

    def busy(self):
        return self.task is not None and not self.task.done()

    def start(self, scenario, full=False, resume_id=None):
        if self.busy():
            raise IntegrationError("busy", "A synchronization is already running.", "Wait for it to finish or stop it first.")
        with self.store.db() as db:
            if resume_id:
                row = db.execute("SELECT * FROM runs WHERE id=?", (resume_id,)).fetchone()
                latest = db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
                if not row or latest[0] != resume_id or row["status"] not in ("failed", "cancelled", "interrupted"):
                    raise IntegrationError("resume", "Only the latest unfinished run can be resumed.", "Start a new run to safely replay from the successful watermark.")
                run_id = resume_id
                db.execute("UPDATE runs SET status='running', ended=NULL, error=NULL, scenario=? WHERE id=?", (scenario, run_id))
            else:
                if db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] >= 100:
                    raise IntegrationError("history_limit", "The local history limit of 100 runs was reached.", "Export records, then reset the workspace.")
                setting = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
                config = Config.model_validate_json(setting["config"])
                since = setting["watermark"] if config.incremental and not full else None
                run_id = uuid.uuid4().hex
                db.execute("INSERT INTO runs(id,status,started,config,scenario,since) VALUES(?,'running',?,?,?,?)",
                           (run_id, now(), setting["config"], scenario, since))
        self.active_id = run_id
        self.task = asyncio.create_task(self.execute(run_id))
        return run_id

    async def execute(self, run_id):
        store = self.store
        store.event(run_id, "info", "started", "Synchronization started from the last committed checkpoint.")
        def event(level, code, message):
            store.event(run_id, level, code, message)
            if code == "retry":
                with store.db() as db:
                    db.execute("UPDATE runs SET retries=retries+1 WHERE id=?", (run_id,))
        try:
            while True:
                with store.db() as db:
                    run = dict(db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
                config = Config.model_validate_json(run["config"])
                if run["pages"] >= config.max_pages:
                    raise IntegrationError("page_limit", "Maximum page count reached before the API ended.", "Check for looping pagination or reset with a larger page limit.")
                token = json.loads(run["token"]) if run["token"] is not None else None
                connector = self.connector_factory(config, self.credential, self.demo_url, run["scenario"], run_id, event)
                page = await connector.fetch(token, run["since"])
                with store.db() as db:
                    # Reject replayed pages before touching records or advancing the checkpoint.
                    if page.records and db.execute("SELECT 1 FROM fingerprints WHERE run_id=? AND fingerprint=?", (run_id, page.fingerprint)).fetchone():
                        raise IntegrationError("pagination", "The API returned a page already seen in this run.", "Pagination may be ignoring its cursor or page parameter. Fix it, then resume.")
                    inserted = updated = unchanged = 0
                    max_stamp = run["max_stamp"]
                    for record in page.records:
                        encoded = json.dumps(record, sort_keys=True)
                        existing = db.execute("SELECT data FROM records WHERE id=?", (record["id"],)).fetchone()
                        if not existing:
                            inserted += 1
                        elif existing[0] == encoded:
                            unchanged += 1
                        else:
                            updated += 1
                        db.execute("INSERT INTO records(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (record["id"], encoded))
                        max_stamp = max(max_stamp or "", record["updated_at"])
                    if db.execute("SELECT COUNT(*) FROM records").fetchone()[0] > 50000:
                        raise IntegrationError("record_limit", "The local limit of 50,000 records was exceeded.", "Export and reset, or narrow the upstream dataset.")
                    db.execute("INSERT OR IGNORE INTO fingerprints VALUES(?,?)", (run_id, page.fingerprint))
                    db.execute("UPDATE runs SET token=?,max_stamp=?,pages=pages+1,seen=seen+?,inserted=inserted+?,updated=updated+?,unchanged=unchanged+? WHERE id=?",
                               (json.dumps(page.next_token), max_stamp, len(page.records), inserted, updated, unchanged, run_id))
                    if page.next_token is None:
                        db.execute("UPDATE runs SET status='completed',ended=? WHERE id=?", (now(), run_id))
                        if max_stamp:
                            db.execute("UPDATE settings SET watermark=? WHERE id=1", (max(max_stamp, run["since"] or ""),))
                store.event(run_id, "info", "page_committed", f"Page {run['pages'] + 1}: {len(page.records)} records committed.", page=run["pages"] + 1)
                if page.next_token is None:
                    store.event(run_id, "info", "completed", "Synchronization complete. Incremental watermark committed.")
                    break
                await asyncio.sleep(0)  # A cancellation point between atomic page transactions.
        except asyncio.CancelledError:
            with store.db() as db:
                db.execute("UPDATE runs SET status='cancelled',ended=? WHERE id=? AND status != 'completed'", (now(), run_id))
            store.event(run_id, "warning", "cancelled", "Synchronization stopped. Committed pages are retained.", "Resume this run to continue from its checkpoint.")
        except IntegrationError as error:
            with store.db() as db:
                db.execute("UPDATE runs SET status='failed',ended=?,error=? WHERE id=?", (now(), error.code, run_id))
            store.event(run_id, "error", error.code, error.message, error.hint, run["pages"] + 1)
        except Exception:
            # Do not persist exception text: upstream payloads and credentials may be present.
            with store.db() as db:
                db.execute("UPDATE runs SET status='failed',ended=?,error='internal' WHERE id=?", (now(), run_id))
            store.event(run_id, "error", "internal", "An internal processing error stopped the run.", "Check database availability. No raw upstream content is logged.")

    async def stop(self):
        if self.busy():
            self.task.cancel()
            await self.task
