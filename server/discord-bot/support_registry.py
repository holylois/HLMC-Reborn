"""Prospective support metadata only. No names, locations, message bodies or deletion API."""
from datetime import datetime, timezone
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3


def iso(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Support timestamps must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


class Registry:
    def __init__(self, file):
        self.path = Path(file)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("Registry must not be a symlink")
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, channel TEXT NOT NULL, created TEXT NOT NULL,
                    resolved TEXT, activity TEXT NOT NULL, held INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, channel TEXT NOT NULL);
            """)
            columns = {row[1] for row in db.execute('PRAGMA table_info(requests)')}
            if 'retention_class' not in columns:
                db.execute("ALTER TABLE requests ADD COLUMN retention_class TEXT NOT NULL DEFAULT 'legacy-review'")
                db.execute("UPDATE requests SET held=1")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def identifier(value):
        text = str(value)
        if not text.isascii() or not text.isdigit() or not 1 <= len(text) <= 22:
            raise ValueError("Invalid Discord identifier")
        return text

    def received(self, message, channel, created, retention_class='legacy-review'):
        if retention_class not in ('routine', 'case', 'legacy-review'):
            raise ValueError('Unknown support retention class')
        message, channel, created = self.identifier(message), self.identifier(channel), iso(created)
        with self.connect() as db:
            prior = db.execute("SELECT channel,created FROM requests WHERE id=?", (message,)).fetchone()
            if prior and prior != (channel, created):
                raise ValueError("Existing request identity differs")
            db.execute("INSERT OR IGNORE INTO requests(id,channel,created,activity,held,retention_class) VALUES(?,?,?,?,?,?)",
                       (message, channel, created, created, int(retention_class != 'routine'), retention_class))
            db.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?)", (message, message, channel))

    def resolve(self, message, channel, when):
        message, channel, when = self.identifier(message), self.identifier(channel), iso(when)
        with self.connect() as db:
            row = db.execute("SELECT created FROM requests WHERE id=? AND channel=?", (message, channel)).fetchone()
            if row is None:
                return False  # Legacy records need review, never guessed dates.
            if when < row[0]:
                raise ValueError("Resolution predates request")
            db.execute("UPDATE requests SET resolved=COALESCE(resolved,?) WHERE id=?", (when, message))
            return True

    def hold(self, message, channel, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Hold must be explicit")
        with self.connect() as db:
            return db.execute("UPDATE requests SET held=?,retention_class=? WHERE id=? AND channel=?",
                              (int(enabled), 'case' if enabled else 'routine', self.identifier(message),
                               self.identifier(channel))).rowcount == 1

    def protect_after_gap(self):
        # Missed Discord events cannot safely be guessed from the old activity timestamp.
        with self.connect() as db:
            return db.execute("UPDATE requests SET held=1,retention_class='legacy-review' WHERE held=0").rowcount

    def touch_message(self, message, channel, when):
        message, channel, when = self.identifier(message), self.identifier(channel), iso(when)
        with self.connect() as db:
            row = db.execute('SELECT request FROM messages WHERE id=? AND channel=?', (message, channel)).fetchone()
            if row is None:
                return False
            created = db.execute('SELECT created FROM requests WHERE id=?', row).fetchone()[0]
            if when < created:
                raise ValueError('Edit predates request')
            db.execute('UPDATE requests SET activity=MAX(activity,?) WHERE id=?', (when, row[0]))
            return True

    def snapshot(self, request):
        request = self.identifier(request)
        with self.connect() as db:
            return self._snapshot(db, request)

    @staticmethod
    def _snapshot(db, request):
        row = db.execute('SELECT id,channel,created,resolved,activity,held,retention_class FROM requests WHERE id=?',
                         (request,)).fetchone()
        if row is None:
            return None
        result = dict(zip(('id','channel','created','resolved','activity','held','retention_class'), row))
        messages = list(db.execute('SELECT id,channel FROM messages WHERE request=? ORDER BY id', (request,)))
        if (request, result['channel']) not in messages or any(channel != result['channel'] for _, channel in messages):
            raise ValueError('Support membership requires review')
        result['messages'] = [message for message, _ in messages]
        return result

    def forget(self, request, expected_snapshot):
        # Called only after the approved provider reports every tracked message absent.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._snapshot(db, self.identifier(request)) != expected_snapshot:
                raise ValueError('Support metadata changed during expiry')
            db.execute('DELETE FROM messages WHERE request=?', (self.identifier(request),))
            db.execute('DELETE FROM requests WHERE id=?', (self.identifier(request),))

    def reply(self, message, channel, referenced_message, when):
        message, channel = self.identifier(message), self.identifier(channel)
        referenced_message, when = self.identifier(referenced_message), iso(when)
        with self.connect() as db:
            row = db.execute("SELECT request FROM messages WHERE id=? AND channel=?",
                             (referenced_message, channel)).fetchone()
            if row is None:
                return False
            created = db.execute("SELECT created FROM requests WHERE id=?", row).fetchone()[0]
            if when < created:
                raise ValueError("Reply predates request")
            db.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?)", (message, row[0], channel))
            db.execute("UPDATE requests SET activity=MAX(activity,?) WHERE id=?", (when, row[0]))
            return True

    def inventory(self):
        with self.connect() as db:
            return self.rows(db)

    @staticmethod
    def rows(db):
        return [{"id": "support-" + key, "created_at": created,
                 "status": "resolved" if resolved else "open", "hold": bool(held),
                 "resolved_at": max(resolved, activity) if resolved else None,
                 "retention_class": category}
                for key, created, resolved, activity, held, category in db.execute(
                    "SELECT id,created,resolved,activity,held,retention_class FROM requests ORDER BY id")]

    @classmethod
    def read_inventory(cls, file):
        file = Path(file)
        if file.is_symlink():
            raise ValueError("Registry must not be a symlink")
        db = sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return cls.rows(db)
        finally:
            db.close()
