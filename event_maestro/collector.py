"""Turn a batch sent by ``web/tracker.js`` into GA4 export rows.

The browser sends one JSON body per flush (like gtag's ``/g/collect`` hits)::

    {
      "client_id": "1716345678.1727330000",      # becomes user_pseudo_id
      "user_id": "reader-42" | null,
      "first_touch_micros": 1727330000000000,
      "user_properties": {"preferred_topic": "lakehouse"},
      "traffic_source": {"source": "google", "medium": "organic", "campaign": null},
      "language": "zh-tw",
      "hostname": "localhost",
      "events": [
        {"name": "page_view", "timestamp_micros": 1727330000123000,
         "user_id": null,                       # optional per-event override
         "params": {"ga_session_id": 1727330000, "page_location": "..."},
         "collected_traffic_source": {...} | null}
      ]
    }
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Any, Mapping

from . import ga4
from .enrich import geo_for_visitor, parse_user_agent

MAX_EVENTS_PER_BATCH = 500


class CollectError(ValueError):
    pass


class Collector:
    def __init__(self, sink, recent_size: int = 200):
        self.sink = sink
        self.recent: collections.deque[dict] = collections.deque(maxlen=recent_size)
        self._lock = threading.Lock()
        self._bundle_seq = 0
        self._last_ts: dict[str, int] = {}

    def collect(self, payload: Mapping[str, Any], user_agent: str) -> list[dict]:
        client_id = payload.get("client_id")
        events = payload.get("events")
        if not isinstance(client_id, str) or not client_id:
            raise CollectError("client_id is required")
        if not isinstance(events, list) or not events:
            raise CollectError("events must be a non-empty list")
        if len(events) > MAX_EVENTS_PER_BATCH:
            raise CollectError(f"at most {MAX_EVENTS_PER_BATCH} events per batch")

        now_micros = time.time_ns() // 1000
        device = parse_user_agent(user_agent)
        device["language"] = (payload.get("language") or "").lower() or None
        device["web_info"]["hostname"] = payload.get("hostname")
        geo = geo_for_visitor(client_id)

        rows = []
        with self._lock:
            self._bundle_seq += 1
            bundle_seq = self._bundle_seq
            latest_client_ts = max(_int(e.get("timestamp_micros")) or now_micros for e in events)
            offset = now_micros - latest_client_ts
            for index, event in enumerate(events):
                name = event.get("name")
                if not isinstance(name, str) or not name:
                    raise CollectError(f"events[{index}].name is required")
                ts = _int(event.get("timestamp_micros")) or now_micros
                previous = self._last_ts.get(client_id)
                self._last_ts[client_id] = ts
                rows.append(
                    ga4.build_event_row(
                        event_name=name,
                        event_timestamp=ts,
                        user_pseudo_id=client_id,
                        params=event.get("params") or {},
                        user_id=event.get("user_id", payload.get("user_id")),
                        user_properties=payload.get("user_properties"),
                        user_first_touch_timestamp=_int(payload.get("first_touch_micros")),
                        device=device,
                        geo=geo,
                        traffic_source=payload.get("traffic_source"),
                        collected_traffic_source=event.get("collected_traffic_source"),
                        event_previous_timestamp=previous,
                        event_bundle_sequence_id=bundle_seq,
                        event_server_timestamp_offset=offset,
                        batch_event_index=index,
                    )
                )
            self.sink.write_many(rows)
            self.sink.flush()
            self.recent.extend(rows)
        return rows

    def recent_rows(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self.recent)[-limit:][::-1]


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
