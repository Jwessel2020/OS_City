import sqlite3
import threading
import json
import time
from pathlib import Path
from typing import Any, Optional
from queue import SimpleQueue

from src.core.metrics import LogEvent, TickEvent, LockEvent, QueueStatEvent, MetricEvent

class SqlLogger:
    """
    Centralized logging facility using a dedicated writer thread.
    
    OS Concepts Demonstrated:
    - Single Writer Principle (One thread writes to DB to avoid locking issues)
    - Producer-Consumer (Subsystems produce logs, Writer consumes)
    - Asynchronous I/O (Logging doesn't block simulation logic)
    """
    
    def __init__(self, db_path: str = "GP/V2/src/data/v2_city.sqlite3"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Unbounded queue for critical logs to prevent deadlock.
        # In a real OS, this would be a Ring Buffer with overwrite.
        self._queue: SimpleQueue[Optional[LogEvent]] = SimpleQueue()
        
        self._writer_thread = threading.Thread(target=self._writer_loop, name="LogWriter", daemon=True)
        self._running = False
        self.run_id = int(time.time())
        
    def start(self):
        self._init_schema()
        self._running = True
        
        # Always ensure we have a valid thread object
        if self._writer_thread is None or not self._writer_thread.is_alive():
            # Thread might be in a stopped state or not created. 
            # We must create a new thread instance if the old one is dead/stopped.
            self._writer_thread = threading.Thread(target=self._writer_loop, name="LogWriter", daemon=True)
            self._writer_thread.start()
        
        # Log the start of a new run
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, started_at) VALUES (?, ?)",
                (self.run_id, time.time())
            )
            
    def stop(self):
        self._running = False
        self._queue.put(None) # Sentinel to stop writer
        self._writer_thread.join(timeout=2.0)
        
    def log(self, event: LogEvent):
        """Public API to log an event."""
        if not self._running:
            return
        self._queue.put(event)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;") # Write-Ahead Logging for concurrency
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY,
                    started_at REAL,
                    ended_at REAL
                );
                
                CREATE TABLE IF NOT EXISTS ticks (
                    run_id INTEGER,
                    subsystem TEXT,
                    seq INTEGER,
                    latency_ms REAL,
                    drift_ms REAL,
                    work_ms REAL,
                    ts_mono REAL,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                
                CREATE TABLE IF NOT EXISTS locks (
                    run_id INTEGER,
                    subsystem TEXT,
                    lock_name TEXT,
                    wait_ms REAL,
                    held_ms REAL,
                    context TEXT,
                    ts_mono REAL
                );
                
                CREATE TABLE IF NOT EXISTS queue_stats (
                    run_id INTEGER,
                    queue_name TEXT,
                    size INTEGER,
                    capacity INTEGER,
                    dropped INTEGER,
                    ts_mono REAL
                );
                
                CREATE TABLE IF NOT EXISTS metrics (
                    run_id INTEGER,
                    subsystem TEXT,
                    payload JSON,
                    ts_mono REAL
                );
            """)

    def _writer_loop(self):
        """Daemon loop that drains the queue and writes to SQLite."""
        conn = self._connect()
        cursor = conn.cursor()
        
        BATCH_SIZE = 50
        while self._running or not self._queue.empty():
            try:
                # Get first item blocking, subsequent items non-blocking for batching
                batch = []
                item = self._queue.get(timeout=1.0)
                
                if item is None: # Sentinel
                    break
                    
                batch.append(item)
                
                # Try to fill batch
                for _ in range(BATCH_SIZE - 1):
                    if self._queue.empty():
                        break
                    next_item = self._queue.get_nowait()
                    if next_item is None:
                        self._running = False
                        break
                    batch.append(next_item)
                
                self._write_batch(cursor, batch)
                conn.commit()
                
            except Exception:
                # Timeout on get() or DB error
                continue
                
        conn.close()

    def _write_batch(self, cursor: sqlite3.Cursor, batch: list[LogEvent]):
        for event in batch:
            if isinstance(event, TickEvent):
                cursor.execute(
                    "INSERT INTO ticks VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event.run_id, event.subsystem, event.tick_seq, 
                     event.latency_ms, event.drift_ms, event.work_time_ms, event.ts_mono)
                )
            elif isinstance(event, LockEvent):
                cursor.execute(
                    "INSERT INTO locks VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event.run_id, event.subsystem, event.lock_name,
                     event.wait_ms, event.held_ms, event.context, event.ts_mono)
                )
            elif isinstance(event, QueueStatEvent):
                cursor.execute(
                    "INSERT INTO queue_stats VALUES (?, ?, ?, ?, ?, ?)",
                    (event.run_id, event.queue_name, event.size,
                     event.capacity, event.dropped, event.ts_mono)
                )
            elif isinstance(event, MetricEvent):
                cursor.execute(
                    "INSERT INTO metrics VALUES (?, ?, ?, ?)",
                    (event.run_id, event.subsystem, json.dumps(event.payload), event.ts_mono)
                )

