import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oil_prices.parser import (
    ParseError,
    estimate_next_prices,
    parse_adjustment_notice,
    parse_city_prices,
    parse_max_change_per_liter,
    parse_notice,
)

FIXTURES = Path(__file__).parent / "fixtures"
BEIJING = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=BEIJING)


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def notice_html(text):
    return f'<div id="youjia"><dl><dt>成都92#汽油</dt><dd>8.98</dd></dl></div><div>{text}</div>'


class ParseCityPricesTests(unittest.TestCase):
    def test_chengdu_prices(self):
        prices = parse_city_prices(read_fixture("chengdu.html"))
        self.assertEqual(prices, {
            "gasoline_92": 8.98,
            "gasoline_95": 9.59,
            "gasoline_98": 10.95,
            "diesel_0": 8.62,
        })

    def test_ganzi_prices_differ_from_chengdu(self):
        prices = parse_city_prices(read_fixture("ganzi.html"))
        self.assertEqual(prices["gasoline_92"], 9.13)
        self.assertEqual(prices["gasoline_95"], 9.75)
        self.assertEqual(prices["gasoline_98"], 11.04)
        self.assertEqual(prices["diesel_0"], 8.79)

    def test_region_label_does_not_affect_prices(self):
        html = read_fixture("chengdu.html")
        self.assertEqual(
            parse_city_prices(html.replace("成都", "兴安盟")),
            parse_city_prices(html),
        )

    def test_missing_grade_becomes_none(self):
        html = read_fixture("chengdu.html").replace(
            "<dl>\n<dt>成都98#汽油</dt>\n<dd>10.95</dd>\n</dl>", ""
        )
        prices = parse_city_prices(html)
        self.assertIsNone(prices["gasoline_98"])
        self.assertEqual(prices["gasoline_92"], 8.98)

    def test_non_positive_price_only_nulls_affected_grade(self):
        html = read_fixture("chengdu.html").replace("<dd>8.62</dd>", "<dd>0</dd>")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            prices = parse_city_prices(html)
        self.assertIsNone(prices["diesel_0"])
        self.assertEqual(prices["gasoline_92"], 8.98)

    def test_invalid_price_only_nulls_affected_grade(self):
        for value in ("", "-", "暂无", "NaN", "inf", "-1"):
            with self.subTest(value=value):
                html = read_fixture("chengdu.html").replace("<dd>10.95</dd>", f"<dd>{value}</dd>")
                with self.assertLogs("oil_prices.parser", level="WARNING"):
                    prices = parse_city_prices(html)
                self.assertEqual(prices, {
                    "gasoline_92": 8.98, "gasoline_95": 9.59,
                    "gasoline_98": None, "diesel_0": 8.62,
                })

    def test_missing_price_element_only_nulls_affected_grade(self):
        html = read_fixture("chengdu.html").replace("<dd>10.95</dd>", "")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            prices = parse_city_prices(html)
        self.assertIsNone(prices["gasoline_98"])
        self.assertEqual(prices["gasoline_92"], 8.98)

    def test_missing_price_block_is_rejected(self):
        with self.assertRaises(ParseError):
            parse_city_prices("<html><body>error</body></html>")

    def test_unrecognised_label_does_not_discard_other_prices(self):
        html = read_fixture("chengdu.html").replace("成都92#汽油", "invalid")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            prices = parse_city_prices(html)
        self.assertIsNone(prices["gasoline_92"])
        self.assertEqual(prices["gasoline_95"], 9.59)

    def test_unknown_grade_does_not_discard_other_prices(self):
        html = read_fixture("chengdu.html").replace("成都92#汽油", "成都93#汽油")
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            prices = parse_city_prices(html)
        self.assertIsNone(prices["gasoline_92"])
        self.assertEqual(prices["gasoline_95"], 9.59)


class ParseNoticeTests(unittest.TestCase):
    def test_up_forecast_and_24h_becomes_next_midnight(self):
        forecast, at = parse_notice(read_fixture("sichuan.html"), NOW)
        self.assertEqual(forecast, "up")
        self.assertEqual(at, "2026-11-13T00:00:00+08:00")

    def test_year_rollover_uses_next_year(self):
        html = notice_html("下次油价1月2日24时调整<br/>目前预计下调油价")
        forecast, at = parse_notice(html, datetime(2026, 12, 30, tzinfo=BEIJING))
        self.assertEqual(forecast, "down")
        self.assertEqual(at, "2027-01-03T00:00:00+08:00")

    def test_date_far_from_now_is_none(self):
        html = notice_html("下次油价6月1日24时调整<br/>目前预计不变")
        forecast, at = parse_notice(html, NOW)
        self.assertEqual(forecast, "unchanged")
        self.assertIsNone(at)

    def test_missing_notice_returns_none(self):
        self.assertEqual(parse_notice("<html></html>", NOW), (None, None))


class ParseAdjustmentNoticeTests(unittest.TestCase):
    def test_exact_sentence_excludes_reminder(self):
        self.assertEqual(
            parse_adjustment_notice(read_fixture("sichuan.html")),
            "目前预计上调油价90元/吨(0.07元/升-0.08元/升)",
        )

    def test_down_notice_with_markup_whitespace_and_fullwidth_brackets(self):
        html = notice_html(
            "目前预计<span>下调油价</span> 100元/吨（0.08元/升-<b>0.09元/升</b>），请关注"
        )
        self.assertEqual(
            parse_adjustment_notice(html),
            "目前预计下调油价100元/吨（0.08元/升-0.09元/升）",
        )

    def test_per_ton_only_and_unchanged(self):
        for text in ("目前预计上调油价90元/吨", "目前预计不变"):
            with self.subTest(text=text):
                self.assertEqual(parse_adjustment_notice(notice_html(text)), text)

    def test_missing_notice_is_null(self):
        with self.assertLogs("oil_prices.parser", level="WARNING"):
            self.assertIsNone(parse_adjustment_notice("<html></html>"))


class ParseMaxChangeTests(unittest.TestCase):
    def test_range_takes_maximum(self):
        self.assertEqual(parse_max_change_per_liter(read_fixture("sichuan.html")), 0.08)

    def test_missing_range_returns_none(self):
        self.assertIsNone(parse_max_change_per_liter("<html></html>"))

    def test_per_ton_only_returns_none(self):
        html = notice_html("下次油价6月1日24时调整<br/>目前预计上调油价90元/吨")
        self.assertIsNone(parse_max_change_per_liter(html))


class EstimateNextPricesTests(unittest.TestCase):
    CURRENT = {"gasoline_92": 8.98, "gasoline_95": 9.59, "gasoline_98": None, "diesel_0": 8.62}

    def test_up_adds_max_change(self):
        result = estimate_next_prices(self.CURRENT, "up", 0.08,
                                      "2026-11-13T00:00:00+08:00", NOW)
        self.assertEqual(result["gasoline_92"], 9.06)
        self.assertEqual(result["gasoline_95"], 9.67)
        self.assertIsNone(result["gasoline_98"])
        self.assertEqual(result["diesel_0"], 8.7)

    def test_down_subtracts_max_change(self):
        result = estimate_next_prices(self.CURRENT, "down", 0.08,
                                      "2026-11-13T00:00:00+08:00", NOW)
        self.assertEqual(result["gasoline_92"], 8.9)

    def test_unchanged_or_unknown_gives_none(self):
        future = "2026-11-13T00:00:00+08:00"
        self.assertEqual(estimate_next_prices(self.CURRENT, "unchanged", 0.08, future, NOW)["gasoline_92"], None)
        self.assertEqual(estimate_next_prices(self.CURRENT, None, 0.08, future, NOW)["gasoline_92"], None)
        self.assertEqual(estimate_next_prices(self.CURRENT, "up", None, future, NOW)["gasoline_92"], None)

    def test_past_adjustment_gives_none(self):
        result = estimate_next_prices(self.CURRENT, "up", 0.08,
                                      "2026-11-01T00:00:00+08:00", NOW)
        self.assertEqual(result["gasoline_92"], None)


if __name__ == "__main__":
    unittest.main()
