"""Write GA4 rows as newline-delimited JSON in Hive-style date partitions.

Layout::

    <output_dir>/raw/ga4_events/event_date=YYYY-MM-DD/<source>-<run>.jsonl

``event_date`` in the path is ISO (``2026-09-26``) so engines such as DuckDB,
Spark and Trino parse it as a DATE; the ``event_date`` field inside each row
keeps GA4's own ``YYYYMMDD`` string.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import IO, Iterable, Mapping

DATASET = "ga4_events"


def default_output_dir() -> Path:
    return Path(os.environ.get("EVENT_MAESTRO_OUTPUT_DIR", "data"))


def partition_dir(output_dir: Path, event_date: str) -> Path:
    iso = f"{event_date[:4]}-{event_date[4:6]}-{event_date[6:]}"
    return output_dir / "raw" / DATASET / f"event_date={iso}"


class JsonlSink:
    """Append rows to one file per ``event_date`` partition.

    Thread-safe so the HTTP collector can share one sink across requests.
    """

    def __init__(self, output_dir: Path | str | None = None, file_stem: str = "events"):
        self.output_dir = Path(output_dir) if output_dir else default_output_dir()
        self.file_stem = file_stem
        self._handles: dict[str, IO[str]] = {}
        self._lock = threading.Lock()
        self.rows_written = 0

    def path_for(self, event_date: str) -> Path:
        return partition_dir(self.output_dir, event_date) / f"{self.file_stem}.jsonl"

    def write(self, row: Mapping) -> None:
        self.write_many([row])

    def write_many(self, rows: Iterable[Mapping]) -> None:
        with self._lock:
            for row in rows:
                handle = self._handles.get(row["event_date"])
                if handle is None:
                    path = self.path_for(row["event_date"])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    handle = path.open("a", encoding="utf-8")
                    self._handles[row["event_date"]] = handle
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                self.rows_written += 1

    def flush(self) -> None:
        with self._lock:
            for handle in self._handles.values():
                handle.flush()

    def close(self) -> None:
        with self._lock:
            for handle in self._handles.values():
                handle.close()
            self._handles.clear()

    def __enter__(self) -> "JsonlSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
