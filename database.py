"""SQLite storage for events (alert history) and security rules."""
import sqlite3
from datetime import datetime
from typing import List, Optional

import pandas as pd

from .models import Alert
from .rules import Rule, parse_time


class Database:
    def __init__(self, path: str = "campus_security.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT    NOT NULL,
                location     TEXT    NOT NULL,
                description  TEXT    NOT NULL,
                severity     INTEGER NOT NULL,
                person_count INTEGER NOT NULL DEFAULT 1,
                category     TEXT    NOT NULL DEFAULT '',
                status       TEXT    NOT NULL DEFAULT 'pending'
            );
            CREATE TABLE IF NOT EXISTS rules (
                location     TEXT PRIMARY KEY,
                allowed_from TEXT NOT NULL,
                allowed_to   TEXT NOT NULL,
                severity     INTEGER NOT NULL,
                enabled      INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        self.conn.commit()

    # ---- events ---------------------------------------------------------
    def add_event(self, a: Alert) -> int:
        cur = self.conn.execute(
            "INSERT INTO events (timestamp, location, description, severity,"
            " person_count, category, status) VALUES (?,?,?,?,?,?,?)",
            (a.timestamp.isoformat(timespec="seconds"), a.location, a.description,
             a.severity, a.person_count, a.category, a.status),
        )
        self.conn.commit()
        return cur.lastrowid

    @staticmethod
    def _row_to_alert(r: sqlite3.Row) -> Alert:
        return Alert(
            id=r["id"], timestamp=datetime.fromisoformat(r["timestamp"]),
            location=r["location"], description=r["description"],
            severity=r["severity"], person_count=r["person_count"],
            category=r["category"], status=r["status"],
        )

    def get_events(self, status: Optional[str] = None, newest_first: bool = True,
                   limit: Optional[int] = None) -> List[Alert]:
        sql = "SELECT * FROM events"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id " + ("DESC" if newest_first else "ASC")
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [self._row_to_alert(r) for r in self.conn.execute(sql, params)]

    def set_status(self, event_id: int, status: str) -> None:
        self.conn.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))
        self.conn.commit()

    def count_events(self, status: Optional[str] = None, min_severity: int = 0) -> int:
        sql = "SELECT COUNT(*) FROM events WHERE severity >= ?"
        params: list = [min_severity]
        if status:
            sql += " AND status = ?"
            params.append(status)
        return self.conn.execute(sql, params).fetchone()[0]

    def events_dataframe(self) -> pd.DataFrame:
        """All events as a Pandas DataFrame (adds an 'hour' column)."""
        df = pd.read_sql_query("SELECT * FROM events ORDER BY id", self.conn)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["hour"] = df["timestamp"].dt.hour
        return df

    # ---- rules ----------------------------------------------------------
    def save_rule(self, r: Rule) -> None:
        self.conn.execute(
            "INSERT INTO rules (location, allowed_from, allowed_to, severity, enabled)"
            " VALUES (?,?,?,?,?) ON CONFLICT(location) DO UPDATE SET"
            " allowed_from=excluded.allowed_from, allowed_to=excluded.allowed_to,"
            " severity=excluded.severity, enabled=excluded.enabled",
            (r.location, r.allowed_from.strftime("%H:%M"), r.allowed_to.strftime("%H:%M"),
             r.severity, int(r.enabled)),
        )
        self.conn.commit()

    def get_rules(self) -> List[Rule]:
        rows = self.conn.execute("SELECT * FROM rules ORDER BY location").fetchall()
        return [Rule(r["location"], parse_time(r["allowed_from"]), parse_time(r["allowed_to"]),
                     r["severity"], bool(r["enabled"])) for r in rows]

    def delete_rule(self, location: str) -> None:
        self.conn.execute("DELETE FROM rules WHERE location=?", (location,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
