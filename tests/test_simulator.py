import collections
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from event_maestro.__main__ import main
from event_maestro.simulator import generate_history
from tests.schema_check import errors


def params(row):
    out = {}
    for p in row["event_params"]:
        v = p["value"]
        out[p["key"]] = next((v[k] for k in ("string_value", "int_value", "double_value", "float_value") if v[k] is not None), None)
    return out


class GenerateHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = list(generate_history(users=120, days=7, end_date=date(2026, 9, 25), seed=1))

    def test_every_row_matches_schema(self):
        for row in self.rows:
            self.assertEqual(errors(row), [], row["event_name"])

    def test_is_deterministic(self):
        again = list(generate_history(users=120, days=7, end_date=date(2026, 9, 25), seed=1))
        self.assertEqual(self.rows, again)

    def test_each_session_starts_with_session_start(self):
        sessions = collections.defaultdict(list)
        for row in self.rows:
            p = params(row)
            sessions[(row["user_pseudo_id"], p["ga_session_id"])].append(row["event_name"])
        for events in sessions.values():
            first = events[1] if events[0] == "first_visit" else events[0]
            self.assertEqual(first, "session_start")

    def test_one_first_visit_per_user(self):
        firsts = collections.Counter(r["user_pseudo_id"] for r in self.rows if r["event_name"] == "first_visit")
        users = {r["user_pseudo_id"] for r in self.rows}
        self.assertEqual(set(firsts), users)
        self.assertEqual(set(firsts.values()), {1})

    def test_read_progress_marks(self):
        marks = {params(r)["percent_read"] for r in self.rows if r["event_name"] == "read_progress"}
        self.assertEqual(marks, {25, 50, 75, 100})

    def test_article_events_carry_article_params(self):
        for row in self.rows:
            if row["event_name"] in ("read_progress", "like_article", "share", "bookmark_article"):
                self.assertIn("article_id", params(row))

    def test_ecommerce_is_empty(self):
        self.assertTrue(all(r["items"] == [] for r in self.rows))

    def test_duplicates(self):
        rows = list(generate_history(users=50, days=3, end_date=date(2026, 9, 25), seed=2, duplicate_rate=0.2))
        keys = [(r["user_pseudo_id"], r["event_timestamp"], r["event_name"]) for r in rows]
        self.assertGreater(len(keys), len(set(keys)))


class CliTest(unittest.TestCase):
    def test_generate_writes_hive_partitions_and_is_rerunnable(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = ["-o", tmp, "generate", "--users", "20", "--days", "3", "--end-date", "2026-09-25"]
            main(args)
            files = sorted(Path(tmp, "raw", "ga4_events").glob("event_date=*/*.jsonl"))
            self.assertTrue(files)
            count = sum(1 for f in files for _ in f.open())
            main(args)
            self.assertEqual(count, sum(1 for f in files for _ in f.open()))
            row = json.loads(files[0].open().readline())
            iso = files[0].parent.name.split("=")[1]
            self.assertEqual(row["event_date"], iso.replace("-", ""))


if __name__ == "__main__":
    unittest.main()
