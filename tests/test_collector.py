import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oil_prices.collector import EXIT_FAILED, EXIT_OK, EXIT_PARTIAL, run

FIXTURES = Path(__file__).parent / "fixtures"
BEIJING = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=BEIJING)
PROVINCE_URL = "http://www.qiyoujiage.com/sichuan.shtml"
CHENGDU_URL = "http://www.qiyoujiage.com/sichuan/chengdu.shtml"
GANZI_URL = "http://www.qiyoujiage.com/sichuan/ganzi.shtml"


class FakeResponse:
    def __init__(self, status_code, text="", url=""):
        self.status_code = status_code
        self.text = text
        self.url = url


class FakeSession:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, headers=None, timeout=None):
        status, text = self.routes[url]
        return FakeResponse(status, text, url)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok_routes(chengdu=None, ganzi=None):
    return {
        PROVINCE_URL: (200, fixture("sichuan.html")),
        CHENGDU_URL: (200, chengdu or fixture("chengdu.html")),
        GANZI_URL: (200, ganzi or fixture("ganzi.html")),
    }


def write_config(directory):
    config = {
        "provinces": [{
            "province": "四川省",
            "province_code": "510000",
            "province_source_url": PROVINCE_URL,
            "cities": [
                {"city_name": "成都市", "city_code": "510100", "source_region_name": "成都",
                 "source_url": CHENGDU_URL},
                {"city_name": "甘孜藏族自治州", "city_code": "513300", "source_region_name": "甘孜",
                 "source_url": GANZI_URL},
            ],
        }]
    }
    path = Path(directory) / "regions.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def no_sleep(_seconds):
    return None


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.config = write_config(self.dir)
        self.data = self.dir / "data"

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, routes, now=NOW):
        return run(self.config, self.data, now=now, session=FakeSession(routes),
                   sleep=no_sleep, delay=0)

    def load(self, name):
        return json.loads((self.data / name).read_text(encoding="utf-8"))

    def test_all_success_writes_province_index_and_status(self):
        code = self.run_with(ok_routes())
        self.assertEqual(code, EXIT_OK)

        province = self.load("provinces/四川省-510000.json")
        self.assertEqual(province["province"], "四川省")
        self.assertEqual(province["currency"], "CNY")
        self.assertEqual(province["next_forecast"], "up")
        self.assertEqual(province["next_adjustment_at"], "2026-11-13T00:00:00+08:00")
        self.assertEqual(province["next_adjustment_notice"],
                         "目前预计上调油价90元/吨(0.07元/升-0.08元/升)")
        self.assertEqual(province["fetched_at"], NOW.astimezone(BEIJING).isoformat())
        cities = {c["city_code"]: c for c in province["cities"]}
        self.assertEqual(cities["510100"]["current_prices"]["gasoline_92"], 8.98)
        self.assertEqual(cities["513300"]["current_prices"]["gasoline_92"], 9.13)
        self.assertEqual(cities["510100"]["next_prices"]["gasoline_92"], 9.06)
        self.assertEqual(cities["510100"]["next_prices"]["diesel_0"], 8.7)

        status = self.load("status.json")
        self.assertEqual(status["overall_status"], "success")
        index = self.load("index.json")
        self.assertTrue(index["configured_provinces_complete"])
        self.assertEqual(index["provinces"][0]["successful_cities"], 2)
        self.assertEqual(index["provinces"][0]["path"], "provinces/四川省-510000.json")
        self.assertFalse((self.data / "provinces" / "510000.json").exists())

    def test_legacy_city_file_is_migrated_and_prices_preserved_on_failure(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        current = self.data / "provinces" / "四川省-510000.json"
        legacy = current.with_name("510000.json")
        current.rename(legacy)
        routes = ok_routes()
        routes[GANZI_URL] = (500, "")
        self.assertEqual(self.run_with(routes), EXIT_PARTIAL)
        self.assertFalse(legacy.exists())
        cities = {c["city_code"]: c for c in self.load("provinces/四川省-510000.json")["cities"]}
        self.assertEqual(cities["513300"]["current_prices"]["gasoline_92"], 9.13)

    def test_legacy_uniform_file_is_migrated_and_prices_preserved_on_failure(self):
        self.configure_uniform_province()
        self.assertEqual(self.run_with({PROVINCE_URL: (200, fixture("sichuan.html"))}), EXIT_OK)
        current = self.data / "provinces" / "四川省-510000.json"
        before = self.load("provinces/四川省-510000.json")
        legacy = current.with_name("510000.json")
        current.rename(legacy)
        self.assertEqual(self.run_with({PROVINCE_URL: (500, "")}), EXIT_FAILED)
        self.assertFalse(legacy.exists())
        self.assertEqual(self.load("provinces/四川省-510000.json")["current_prices"],
                         before["current_prices"])

    def test_city_failure_keeps_previous_prices_and_exits_partial(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        routes = ok_routes()
        routes[GANZI_URL] = (500, "")
        code = self.run_with(routes)
        self.assertEqual(code, EXIT_PARTIAL)

        cities = {c["city_code"]: c for c in self.load("provinces/四川省-510000.json")["cities"]}
        self.assertEqual(cities["513300"]["current_prices"]["gasoline_92"], 9.13)
        status = self.load("status.json")
        self.assertEqual(status["overall_status"], "partial")
        self.assertTrue(status["regions"]["513300"]["stale"])
        self.assertIsNotNone(status["regions"]["513300"]["error"])
        index = self.load("index.json")
        self.assertEqual(index["provinces"][0]["missing_cities"], ["513300"])

    def test_province_page_failure_preserves_previous_notice(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        before = self.load("provinces/四川省-510000.json")["next_adjustment_notice"]
        routes = ok_routes()
        routes[PROVINCE_URL] = (500, "")
        self.assertEqual(self.run_with(routes), EXIT_PARTIAL)
        self.assertEqual(self.load("provinces/四川省-510000.json")["next_adjustment_notice"], before)

    def test_missing_notice_clears_previous_notice(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        routes = ok_routes()
        routes[PROVINCE_URL] = (200, "<html></html>")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            self.assertEqual(self.run_with(routes), EXIT_OK)
        self.assertIsNone(self.load("provinces/四川省-510000.json")["next_adjustment_notice"])

    def test_invalid_city_grade_writes_other_prices_and_nulls_next_price(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        html = fixture("chengdu.html").replace("<dd>10.95</dd>", "<dd>-</dd>")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            self.assertEqual(self.run_with(ok_routes(chengdu=html)), EXIT_OK)
        city = next(c for c in self.load("provinces/四川省-510000.json")["cities"]
                    if c["city_code"] == "510100")
        self.assertEqual(city["current_prices"]["gasoline_92"], 8.98)
        self.assertEqual(city["current_prices"]["gasoline_95"], 9.59)
        self.assertIsNone(city["current_prices"]["gasoline_98"])
        self.assertIsNone(city["next_prices"]["gasoline_98"])
        self.assertFalse(self.load("status.json")["regions"]["510100"]["stale"])

    def test_invalid_uniform_grade_writes_other_prices(self):
        self.configure_uniform_province()
        html = fixture("chengdu.html").replace("<dd>10.95</dd>", "<dd>-</dd>")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            self.assertEqual(self.run_with({PROVINCE_URL: (200, html)}), EXIT_OK)
        province = self.load("provinces/四川省-510000.json")
        self.assertEqual(province["current_prices"]["gasoline_92"], 8.98)
        self.assertIsNone(province["current_prices"]["gasoline_98"])
        self.assertIsNone(province["next_prices"]["gasoline_98"])

    def test_configured_url_prices_are_used_despite_region_label(self):
        routes = ok_routes(chengdu=fixture("ganzi.html"))
        code = self.run_with(routes)
        self.assertEqual(code, EXIT_OK)
        cities = {c["city_code"]: c for c in self.load("provinces/四川省-510000.json")["cities"]}
        self.assertEqual(cities["510100"]["city_name"], "成都市")
        self.assertEqual(cities["510100"]["source_url"], CHENGDU_URL)
        self.assertEqual(cities["510100"]["current_prices"]["gasoline_92"], 9.13)
        status = self.load("status.json")["regions"]["510100"]
        self.assertIsNone(status["error"])
        self.assertFalse(status["stale"])
        self.assertEqual(status["last_success_at"], NOW.isoformat())

    def test_403_stops_run_and_keeps_existing_province_file(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        before = (self.data / "provinces" / "四川省-510000.json").read_text(encoding="utf-8")

        routes = ok_routes()
        routes[CHENGDU_URL] = (403, "")
        code = self.run_with(routes, now=NOW + timedelta(days=1))
        self.assertEqual(code, EXIT_FAILED)
        after = (self.data / "provinces" / "四川省-510000.json").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertEqual(self.load("status.json")["overall_status"], "failed")

    def test_disallowed_host_is_fatal(self):
        bad_config = write_config(self.dir)
        config = json.loads(bad_config.read_text(encoding="utf-8"))
        config["provinces"][0]["cities"][0]["source_url"] = "http://example.com/sichuan/chengdu.shtml"
        bad_config.write_text(json.dumps(config), encoding="utf-8")
        routes = ok_routes()
        routes["http://example.com/sichuan/chengdu.shtml"] = (200, fixture("chengdu.html"))
        code = run(bad_config, self.data, now=NOW, session=FakeSession(routes),
                   sleep=no_sleep, delay=0)
        self.assertEqual(code, EXIT_FAILED)

    def configure_uniform_province(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["provinces"][0]["uniform_pricing"] = True
        config["provinces"][0]["source_region_name"] = "四川省"
        self.config.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    def test_uniform_province_fetches_only_province_page(self):
        self.configure_uniform_province()
        # Only the province page is routed; any city request raises KeyError.
        routes = {PROVINCE_URL: (200, fixture("sichuan.html"))}
        code = self.run_with(routes)
        self.assertEqual(code, EXIT_OK)

        province = self.load("provinces/四川省-510000.json")
        self.assertTrue(province["uniform_pricing"])
        self.assertEqual(province["next_adjustment_notice"],
                         "目前预计上调油价90元/吨(0.07元/升-0.08元/升)")
        self.assertEqual(province["cities"], [])
        self.assertIsNotNone(province["current_prices"]["gasoline_92"])
        self.assertEqual(province["fetched_at"], NOW.astimezone(BEIJING).isoformat())
        index = self.load("index.json")["provinces"][0]
        for key in ("expected_cities", "successful_cities", "missing_cities"):
            self.assertNotIn(key, index)
        self.assertTrue(index["province_page_ok"])
        status = self.load("status.json")["regions"]
        self.assertEqual(set(status), {"510000"})
        self.assertIsNone(status["510000"]["error"])
        self.assertFalse(status["510000"]["stale"])
        self.assertEqual(status["510000"]["last_success_at"], NOW.isoformat())

    def test_uniform_province_failure_keeps_previous_prices_and_success_time(self):
        self.configure_uniform_province()
        self.assertEqual(self.run_with({PROVINCE_URL: (200, fixture("sichuan.html"))}), EXIT_OK)
        before = self.load("provinces/四川省-510000.json")
        later = NOW + timedelta(days=1)
        code = self.run_with({PROVINCE_URL: (500, "")}, now=later)
        self.assertEqual(code, EXIT_FAILED)
        province = self.load("provinces/四川省-510000.json")
        self.assertEqual(province["current_prices"], before["current_prices"])
        self.assertEqual(province["next_adjustment_notice"], before["next_adjustment_notice"])
        self.assertEqual(province["fetched_at"], before["fetched_at"])
        status = self.load("status.json")["regions"]
        self.assertEqual(set(status), {"510000"})
        self.assertEqual(status["510000"]["last_attempt_at"], later.isoformat())
        self.assertEqual(status["510000"]["last_success_at"], NOW.isoformat())
        self.assertIsNotNone(status["510000"]["error"])
        self.assertTrue(status["510000"]["stale"])
        self.assertFalse(self.load("index.json")["provinces"][0]["province_page_ok"])

    def test_switching_to_uniform_pricing_removes_old_city_statuses(self):
        self.assertEqual(self.run_with(ok_routes()), EXIT_OK)
        self.configure_uniform_province()
        self.assertEqual(self.run_with({PROVINCE_URL: (200, fixture("sichuan.html"))}), EXIT_OK)
        self.assertEqual(set(self.load("status.json")["regions"]), {"510000"})

    def test_uniform_province_first_failure_is_not_stale(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["provinces"][0]["uniform_pricing"] = True
        config["provinces"][0]["cities"] = []
        self.config.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.run_with({PROVINCE_URL: (500, "")}), EXIT_FAILED)
        status = self.load("status.json")["regions"]
        self.assertEqual(set(status), {"510000"})
        self.assertIsNone(status["510000"]["last_success_at"])
        self.assertIsNotNone(status["510000"]["error"])
        self.assertFalse(status["510000"]["stale"])


if __name__ == "__main__":
    unittest.main()
