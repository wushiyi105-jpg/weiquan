"""SQLite:存每次维权记录的类目、时效与文书,便于跟进同一单的多轮沟通。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "weiquan.db")


class Database:
    def __init__(self, path=None):
        self.path = path or os.environ.get("WEIQUAN_DB") or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT, sign TEXT, days INTEGER,
                    missing INTEGER, detail TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            self.conn.commit()

    def save(self, result):
        cats = "、".join(c["name"] for c in result["categories"])
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO cases (category, sign, days, missing, detail) VALUES (?,?,?,?,?)",
                (cats, result["timeline"]["sign"], result["timeline"]["days"],
                 len(result["evidence"]["missing"]), json.dumps(result, ensure_ascii=False)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def latest(self, limit=10):
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, category, sign, days, missing, created_at FROM cases "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
