import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from event_maestro.collector import CollectError, Collector
from event_maestro.server import make_handler
from event_maestro.sink import JsonlSink
from tests.schema_check import errors

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1"


def payload(**kw):
    body = {
        "client_id": "111.1790000000",
        "user_id": None,
        "first_touch_micros": 1_790_000_000_000_000,
        "user_properties": {},
        "traffic_source": {"source": "google", "medium": "organic", "campaign": "(organic)"},
        "language": "zh-TW",
        "hostname": "localhost",
        "events": [
            {"name": "session_start", "timestamp_micros": 1_790_000_000_100_000,
             "params": {"ga_session_id": 1790000000, "ga_session_number": 1},
             "collected_traffic_source": {"source": "google", "medium": "organic"}},
            {"name": "page_view", "timestamp_micros": 1_790_000_000_200_000,
             "params": {"ga_session_id": 1790000000, "ga_session_number": 1, "page_location": "http://localhost/"}},
        ],
    }
    body.update(kw)
    return body


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sink = JsonlSink(self.tmp.name, file_stem="collector")
        self.collector = Collector(self.sink)

    def tearDown(self):
        self.sink.close()
        self.tmp.cleanup()

    def test_rows_are_enriched_and_valid(self):
        rows = self.collector.collect(payload(), UA)
        self.assertEqual([r["event_name"] for r in rows], ["session_start", "page_view"])
        for row in rows:
            self.assertEqual(errors(row), [])
        self.assertEqual(rows[0]["device"]["category"], "mobile")
        self.assertEqual(rows[0]["device"]["language"], "zh-tw")
        self.assertEqual(rows[1]["event_previous_timestamp"], rows[0]["event_timestamp"])
        self.assertEqual([r["batch_event_index"] for r in rows], [0, 1])
        self.assertEqual(rows[0]["traffic_source"]["source"], "google")

    def test_rows_land_in_partition(self):
        self.collector.collect(payload(), UA)
        files = list(Path(self.tmp.name, "raw", "ga4_events").glob("event_date=*/collector.jsonl"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(files[0].read_text().splitlines()), 2)

    def test_event_level_user_id_wins(self):
        body = payload(user_id="reader-1")
        body["events"][0]["user_id"] = None
        rows = self.collector.collect(body, UA)
        self.assertEqual([r["user_id"] for r in rows], [None, "reader-1"])

    def test_rejects_bad_payloads(self):
        with self.assertRaises(CollectError):
            self.collector.collect(payload(client_id=""), UA)
        with self.assertRaises(CollectError):
            self.collector.collect(payload(events=[]), UA)


class ServerTest(unittest.TestCase):
    def test_collect_and_static_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sink = JsonlSink(tmp, file_stem="collector")
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Collector(sink)))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_port}"
            try:
                req = urllib.request.Request(base + "/collect", data=json.dumps(payload()).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": UA})
                self.assertEqual(json.load(urllib.request.urlopen(req)), {"accepted": 2})
                articles = json.load(urllib.request.urlopen(base + "/api/articles"))
                self.assertGreaterEqual(len(articles["articles"]), 10)
                page = urllib.request.urlopen(base + "/articles/a001").read().decode()
                self.assertIn("tracker.js", page)
                recent = json.load(urllib.request.urlopen(base + "/api/recent"))
                self.assertEqual(recent["rows"][0]["event_name"], "page_view")
            finally:
                httpd.shutdown()
                httpd.server_close()
                sink.close()


if __name__ == "__main__":
    unittest.main()
