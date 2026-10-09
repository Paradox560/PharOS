"""Local application state, separate from the workshop's immutable archive/index."""
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from backend.models import utcnow


class Store:
    def __init__(self, path: str):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        with self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('CREATE TABLE IF NOT EXISTS entities (kind TEXT, id TEXT, body TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(kind,id))')
            self.db.execute('CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, job_id TEXT NOT NULL)')
            self.db.execute('PRAGMA user_version=1')

    def put(self, kind: str, item: dict[str, Any], *, insert_only=False):
        verb = 'INSERT OR IGNORE' if insert_only else 'INSERT OR REPLACE'
        with self.lock, self.db:
            self.db.execute(f'{verb} INTO entities VALUES (?,?,?,?)', (kind, item['id'], json.dumps(item, allow_nan=False), utcnow()))
        return item

    def get(self, kind: str, id: str) -> dict | None:
        with self.lock:
            row = self.db.execute('SELECT body FROM entities WHERE kind=? AND id=?', (kind, id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str, limit: int = 1000) -> list[dict]:
        with self.lock:
            rows = self.db.execute('SELECT body FROM entities WHERE kind=? ORDER BY updated_at DESC,id LIMIT ?', (kind, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def mutate(self, kind: str, id: str, update):
        with self.lock:
            existing = self.get(kind, id)
            if existing is None:
                return None
            return self.put(kind, update(existing))

    def remember_request(self, key: str, fingerprint: str, job_id: str):
        with self.lock, self.db:
            self.db.execute('INSERT INTO idempotency VALUES (?,?,?)', (key, fingerprint, job_id))

    def find_request(self, key: str):
        with self.lock:
            row = self.db.execute('SELECT fingerprint,job_id FROM idempotency WHERE key=?', (key,)).fetchone()
        return row

    def fail_interrupted_jobs(self):
        for job in self.list('jobs'):
            if job['state'] in {'queued', 'running'}:
                job.update(state='failed', updated_at=utcnow(), error={'code': 'worker_restarted', 'message': 'Application restarted; remote re-ingestion may still be running. Check upstream state before retrying.'})
                self.put('jobs', job)

    def close(self):
        with self.lock:
            self.db.close()

    def prune(self, kind, before):
        with self.lock, self.db:
            self.db.execute('DELETE FROM entities WHERE kind=? AND updated_at<?', (kind, before))
