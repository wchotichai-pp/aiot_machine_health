"""เก็บข้อมูลลง SQLite (มีเวลาทุกแถว ต่างจากใบงาน 5 ที่ไม่ได้เก็บเวลา)"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    device_id   TEXT PRIMARY KEY,
    config      TEXT NOT NULL,
    first_seen  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    seq       INTEGER,
    vib_rms   REAL NOT NULL,
    vib_peak  REAL NOT NULL,
    temp      REAL,
    hum       REAL,
    rssi      INTEGER,
    state     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_dev_ts ON readings(device_id, ts);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    kind      TEXT NOT NULL,
    state     TEXT,
    message   TEXT NOT NULL
);
"""

READING_COLS = ("id", "device_id", "ts", "seq", "vib_rms", "vib_peak", "temp", "hum", "rssi", "state")
EVENT_COLS = ("id", "device_id", "ts", "kind", "state", "message")


class Store:
    def __init__(self, path: str, retention_days: int = 7):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._retention_s = retention_days * 86400
        self._inserts = 0

    # ---------- เครื่องจักร ----------
    def load_machines(self) -> dict[str, dict]:
        with self._lock:
            rows = self._db.execute("SELECT device_id, config FROM machines").fetchall()
        return {d: json.loads(c) for d, c in rows}

    def save_machine(self, device_id: str, config: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO machines(device_id, config, first_seen) VALUES(?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET config=excluded.config",
                (device_id, json.dumps(config), time.time()),
            )

    # ---------- ค่าที่วัดได้ ----------
    def add_reading(self, device_id: str, ts: float, seq: int, vib_rms: float, vib_peak: float,
                    temp, hum, rssi, state: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO readings(device_id, ts, seq, vib_rms, vib_peak, temp, hum, rssi, state) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (device_id, ts, seq, vib_rms, vib_peak, temp, hum, rssi, state),
            )
            self._inserts += 1
            if self._inserts % 1000 == 0:
                self._db.execute("DELETE FROM readings WHERE ts < ?", (ts - self._retention_s,))

    def latest_reading(self, device_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                f"SELECT {','.join(READING_COLS)} FROM readings WHERE device_id=? ORDER BY id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        return dict(zip(READING_COLS, row)) if row else None

    def history(self, device_id: str, since_ts: float, limit: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {','.join(READING_COLS)} FROM readings WHERE device_id=? AND ts>=? "
                "ORDER BY id DESC LIMIT ?",
                (device_id, since_ts, limit),
            ).fetchall()
        return [dict(zip(READING_COLS, r)) for r in reversed(rows)]

    # ---------- เหตุการณ์ ----------
    def add_event(self, device_id: str, ts: float, kind: str, state: str | None, message: str) -> int:
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO events(device_id, ts, kind, state, message) VALUES(?,?,?,?,?)",
                (device_id, ts, kind, state, message),
            )
            return int(cur.lastrowid)

    def events(self, after_id: int = 0, limit: int = 50, device_id: str | None = None) -> list[dict]:
        sql = f"SELECT {','.join(EVENT_COLS)} FROM events WHERE id>?"
        args: list = [after_id]
        if device_id:
            sql += " AND device_id=?"
            args.append(device_id)
        if after_id:
            sql += " ORDER BY id ASC LIMIT ?"
        else:
            sql = f"SELECT * FROM ({sql} ORDER BY id DESC LIMIT ?) ORDER BY id ASC"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [dict(zip(EVENT_COLS, r)) for r in rows]

    def last_event_id(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
        return int(row[0])
