import json
import unittest
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "regions.json"
ALLOWED_PREFIX = "http://www.qiyoujiage.com/"


class RegionsConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CONFIG.open(encoding="utf-8") as f:
            cls.provinces = json.load(f)["provinces"]

    def test_covers_all_31_provinces(self):
        self.assertEqual(len(self.provinces), 31)
        self.assertEqual(len({p["province_code"] for p in self.provinces}), 31)

    def test_codes_are_unique_six_digit_strings(self):
        codes = [p["province_code"] for p in self.provinces]
        codes += [c["city_code"] for p in self.provinces for c in p["cities"]]
        for code in codes:
            self.assertRegex(code, r"^\d{6}$")
        province_codes = [p["province_code"] for p in self.provinces]
        city_codes = [c["city_code"] for p in self.provinces for c in p["cities"]]
        self.assertEqual(len(set(city_codes)), len(city_codes))
        self.assertEqual(len(set(province_codes)), len(province_codes))

    def test_every_city_has_label_and_allowed_url(self):
        for p in self.provinces:
            self.assertTrue(p["province_source_url"].startswith(ALLOWED_PREFIX),
                            p["province_source_url"])
            if p["uniform_pricing"]:
                self.assertEqual(p["cities"], [], p["province"])
            else:
                self.assertTrue(p["cities"], p["province"])
            for c in p["cities"]:
                self.assertTrue(c["source_region_name"], c["city_name"])
                self.assertTrue(c["source_url"].startswith(ALLOWED_PREFIX), c["source_url"])

    def test_uniform_provinces_only_have_province_records(self):
        self.assertEqual(sum(p["uniform_pricing"] for p in self.provinces), 21)
        self.assertEqual(sum(len(p["cities"]) for p in self.provinces), 125)
        hebei = next(p for p in self.provinces if p["province_code"] == "130000")
        self.assertTrue(hebei["uniform_pricing"])
        self.assertEqual(hebei["cities"], [])


if __name__ == "__main__":
    unittest.main()
