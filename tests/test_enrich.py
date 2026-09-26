import unittest

from event_maestro.enrich import geo_for_visitor, parse_user_agent


class ParseUserAgentTest(unittest.TestCase):
    def test_desktop_chrome_on_windows(self):
        d = parse_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
        self.assertEqual((d["category"], d["operating_system"], d["web_info"]["browser"]), ("desktop", "Windows", "Chrome"))
        self.assertEqual(d["operating_system_version"], "Windows 10")

    def test_iphone_safari(self):
        d = parse_user_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1")
        self.assertEqual((d["category"], d["operating_system"], d["mobile_model_name"]), ("mobile", "iOS", "iPhone"))
        self.assertEqual(d["web_info"], {"browser": "Safari", "browser_version": "17.6"})

    def test_edge_is_not_reported_as_chrome(self):
        d = parse_user_agent("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0")
        self.assertEqual(d["web_info"]["browser"], "Edge")

    def test_samsung_android_phone(self):
        d = parse_user_agent("Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36")
        self.assertEqual((d["category"], d["mobile_brand_name"], d["web_info"]["browser"]), ("mobile", "Samsung", "Samsung Internet"))


class GeoTest(unittest.TestCase):
    def test_geo_is_stable_per_visitor(self):
        self.assertEqual(geo_for_visitor("123.456"), geo_for_visitor("123.456"))
        self.assertIn("country", geo_for_visitor("abc"))


if __name__ == "__main__":
    unittest.main()
