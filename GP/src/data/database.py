"""SQLite persistence layer for simulation metrics and controls."""

from __future__ import annotations

import argparse
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


from src.utils import trace

class SimulationDatabase:
    """Small helper around sqlite3 for persisting simulation data."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        enable_wal: bool = True,
        log_path: str | Path | None = "logs/sqlite_trace.log",
    ) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._log_path = Path(log_path) if log_path else None
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,  # autocommit mode
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        if enable_wal:
            self._conn.execute("PRAGMA journal_mode = WAL;")
        if self._log_path is not None:
            self._conn.set_trace_callback(self._trace_sql)
        self._initialize_schema()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------
    def _initialize_schema(self) -> None:
        """Create tables if they do not already exist."""

        statements: Sequence[str] = (
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                tick_duration REAL NOT NULL,
                max_ticks INTEGER,
                config_json TEXT,
                status TEXT DEFAULT 'running',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                tick INTEGER NOT NULL,
                subsystem TEXT NOT NULL,
                payload TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS control_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            """,
        )

        with self._lock:
            cursor = self._conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            cursor.close()

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------
    def start_run(
        self,
        *,
        label: str | None,
        tick_duration: float,
        max_ticks: int | None,
        config: dict[str, Any],
    ) -> int:
        """Insert a new run row and return its identifier."""

        payload = json.dumps(config, sort_keys=True)
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO runs (label, tick_duration, max_ticks, config_json)
                VALUES (?, ?, ?, ?)
                """,
                (label, float(tick_duration), max_ticks, payload),
            )
            run_id = int(cursor.lastrowid)
        self._log_event(
            "start_run",
            {"run_id": run_id, "label": label, "tick_duration": tick_duration, "max_ticks": max_ticks},
        )
        return run_id

    def complete_run(self, run_id: int, status: str = "completed") -> None:
        """Mark a run as completed or terminated."""

        with self._lock:
            self._conn.execute(
                """
                UPDATE runs
                SET status = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, run_id),
            )
        self._log_event("complete_run", {"run_id": run_id, "status": status})

    # ------------------------------------------------------------------
    # Data insertion helpers
    # ------------------------------------------------------------------
    def record_metrics(self, run_id: int, tick: int, subsystem: str, metrics: dict[str, Any]) -> None:
        """Persist a metrics snapshot for a subsystem."""

        payload = json.dumps(metrics, sort_keys=True)
        trace.log_event("LOCK", "DATABASE: Acquiring lock for WRITE (Metrics)")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO metrics (run_id, tick, subsystem, payload)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, tick, subsystem, payload),
            )
        trace.log_event("LOCK", "DATABASE: Released lock (Metrics)")
        self._log_event(
            "record_metrics",
            {"run_id": run_id, "tick": tick, "subsystem": subsystem, "payload": metrics},
        )

    def record_control_event(self, run_id: int, controls: dict[str, Any]) -> None:
        """Persist a control-state update coming from the UI or CLI."""

        payload = json.dumps(controls, sort_keys=True)
        trace.log_event("LOCK", "DATABASE: Acquiring lock for WRITE (Control)")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO control_events (run_id, payload)
                VALUES (?, ?)
                """,
                (run_id, payload),
            )
        trace.log_event("LOCK", "DATABASE: Released lock (Control)")
        self._log_event("control_event", {"run_id": run_id, "payload": controls})

    def get_metrics_count(self, run_id: int) -> int:
        """Demonstrate READING from the database during runtime."""
        trace.log_event("LOCK", "DATABASE: Acquiring lock for READ (Count)")
        with self._lock:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM metrics WHERE run_id = ?", (run_id,)
            )
            count = cursor.fetchone()[0]
        trace.log_event("LOCK", "DATABASE: Released lock (Count)")
        return count

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    def list_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        """Return the most recent runs for quick inspection."""

        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT id, label, status, started_at, completed_at, max_ticks
                FROM runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return rows

    def purge(self) -> None:
        """Remove all persisted data (useful for demos/tests)."""

        with self._lock:
            self._conn.execute("DELETE FROM control_events;")
            self._conn.execute("DELETE FROM metrics;")
            self._conn.execute("DELETE FROM runs;")
        self._log_event("purge", {"path": str(self.path)})

    def latest_run(self) -> sqlite3.Row | None:
        """Return the most recent run row."""

        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT id, label, status, tick_duration, max_ticks, started_at, completed_at
                FROM runs
                ORDER BY id DESC
                LIMIT 1
                """
            )
            return cursor.fetchone()

    def latest_metrics(self, limit: int = 5) -> list[sqlite3.Row]:
        """Return most recent metric events."""

        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT run_id, tick, subsystem, payload, recorded_at
                FROM metrics
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cursor.fetchall()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SimulationDatabase:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------
    def _trace_sql(self, statement: str) -> None:
        # self._log_event("sql", {"statement": statement})
        trace.log_event("DATABASE", "Executing SQL", payload=statement.strip())

    def _log_event(self, event: str, payload: dict[str, Any] | None) -> None:
        if self._log_path is None:
            return
        record = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds"),
            "event": event,
            "data": payload or {},
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._log_lock:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def _cli(argv: Iterable[str] | None = None) -> None:
    """Small helper CLI to initialise or inspect the database."""

    parser = argparse.ArgumentParser(description="Initialise or inspect the simulation database.")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("artifacts/smart_city.sqlite3"),
        help="Where the SQLite file should live (default: artifacts/smart_city.sqlite3)",
    )
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="Print a short summary of the most recent runs.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Show the most recent run and a few of its metric events.",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Delete all existing data before exiting.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    db = SimulationDatabase(args.path)
    try:
        if args.purge:
            db.purge()
            print("Database tables cleared.")

        if args.list_runs:
            runs = db.list_runs()
            if not runs:
                print("No runs recorded yet.")
            for row in runs:
                label = row["label"] or "<unnamed>"
                status = row["status"]
                started = row["started_at"]
                completed = row["completed_at"] or "-"
                max_ticks = row["max_ticks"] if row["max_ticks"] is not None else "∞"
                print(f"Run #{row['id']:04d} [{status}] label={label} ticks={max_ticks} started={started} completed={completed}")
        elif args.latest:
            run = db.latest_run()
            if run is None:
                print("No runs recorded yet.")
            else:
                label = run["label"] or "<unnamed>"
                status = run["status"]
                completed = run["completed_at"] or "-"
                print(
                    f"Latest run #{run['id']:04d} [{status}] label={label} ticks={run['max_ticks'] or '∞'} "
                    f"started={run['started_at']} completed={completed}"
                )
                print("- recent metrics -")
                for entry in db.latest_metrics(limit=5):
                    print(
                        f"tick {entry['tick']:03d} :: {entry['subsystem']} :: {entry['recorded_at']} "
                        f"{entry['payload']}"
                    )
        elif not args.purge:
            print(f"Database ready at {args.path.resolve()}")
    finally:
        db.close()


if __name__ == "__main__":
    _cli()


