import unittest
from datetime import timezone

from event_maestro import ga4
from tests.schema_check import errors


class EncodeValueTest(unittest.TestCase):
    def test_types_land_in_the_ga4_slot(self):
        self.assertEqual(ga4.encode_value("x")["string_value"], "x")
        self.assertEqual(ga4.encode_value(3)["int_value"], 3)
        self.assertEqual(ga4.encode_value(True)["int_value"], 1)
        self.assertEqual(ga4.encode_value(1.5)["double_value"], 1.5)
        self.assertIsNone(ga4.encode_value(1.5)["float_value"])

    def test_none_params_are_dropped(self):
        encoded = ga4.encode_params({"a": 1, "b": None})
        self.assertEqual([p["key"] for p in encoded], ["a"])


class BuildRowTest(unittest.TestCase):
    def row(self, **kw):
        base = dict(event_name="page_view", event_timestamp=1_790_000_000_000_000, user_pseudo_id="1.2")
        base.update(kw)
        return ga4.build_event_row(**base)

    def test_minimal_row_matches_schema(self):
        self.assertEqual(errors(self.row()), [])

    def test_event_date_uses_property_time_zone(self):
        # 2026-09-25 17:00 UTC is already 2026-09-26 01:00 in Asia/Taipei.
        ts = 1_790_355_600_000_000
        self.assertEqual(ga4.event_date_for(ts, timezone.utc), "20260925")
        self.assertEqual(self.row(event_timestamp=ts)["event_date"], "20260926")

    def test_traffic_source_defaults_to_direct(self):
        self.assertEqual(self.row()["traffic_source"], {"name": "(direct)", "medium": "(none)", "source": "(direct)"})
        self.assertIsNone(self.row()["collected_traffic_source"])

    def test_collected_traffic_source_maps_utm_fields(self):
        row = self.row(collected_traffic_source={"source": "newsletter", "medium": "email", "campaign": "weekly_digest"})
        self.assertEqual(row["collected_traffic_source"]["manual_source"], "newsletter")
        self.assertEqual(row["collected_traffic_source"]["manual_campaign_name"], "weekly_digest")
        self.assertEqual(errors(row), [])

    def test_user_properties_carry_set_timestamp(self):
        row = self.row(user_properties={"newsletter_subscriber": "yes"})
        self.assertEqual(row["user_properties"][0]["value"]["set_timestamp_micros"], row["event_timestamp"])


if __name__ == "__main__":
    unittest.main()
