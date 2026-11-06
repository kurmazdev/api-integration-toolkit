import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import Config


def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL, watermark TEXT);
            CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
              config TEXT NOT NULL, scenario TEXT NOT NULL, since TEXT, token TEXT, max_stamp TEXT,
              pages INTEGER DEFAULT 0, seen INTEGER DEFAULT 0, inserted INTEGER DEFAULT 0, updated INTEGER DEFAULT 0,
              unchanged INTEGER DEFAULT 0, retries INTEGER DEFAULT 0, error TEXT);
            CREATE TABLE IF NOT EXISTS fingerprints (run_id TEXT, fingerprint TEXT, PRIMARY KEY(run_id, fingerprint));
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, time TEXT NOT NULL,
              level TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL, hint TEXT, page INTEGER);
            ''')
            db.execute("INSERT OR IGNORE INTO settings(id,config) VALUES(1,?)", (Config().model_dump_json(),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def config(self):
        with self.db() as db:
            return dict(db.execute("SELECT * FROM settings WHERE id=1").fetchone())

    def event(self, run_id, level, code, message, hint=None, page=None):
        with self.db() as db:
            db.execute("INSERT INTO events(run_id,time,level,code,message,hint,page) VALUES(?,?,?,?,?,?,?)",
                       (run_id, now(), level, code, message, hint, page))

    def run(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result.pop("config")
            result["events"] = [dict(r) for r in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY id DESC LIMIT 200", (run_id,))]
            return result

    def recover(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM runs WHERE status IN ('running','cancelling')")]
            db.execute("UPDATE runs SET status='interrupted', ended=? WHERE status IN ('running','cancelling')", (now(),))
        for run_id in ids:
            self.event(run_id, "warning", "interrupted", "Process stopped before the run finished.", "Resume from the last committed page; provide credentials again if needed.")

    def records(self, limit=100, offset=0):
        with self.db() as db:
            count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM records ORDER BY id LIMIT ? OFFSET ?", (limit, offset))]
        return {"total": count, "items": rows}
