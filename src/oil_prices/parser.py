"""Pure HTML parsing for qiyoujiage.com pages (no network access)."""

import logging
import math
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

GRADE_KEYS = {
    "92": "gasoline_92",
    "95": "gasoline_95",
    "98": "gasoline_98",
    "0": "diesel_0",
}

FORECAST_KEYS = {
    "上调": "up",
    "上涨": "up",
    "下调": "down",
    "下跌": "down",
    "不变": "unchanged",
    "维持": "unchanged",
}

MAX_ADJUSTMENT_DISTANCE = timedelta(days=45)

_LABEL_RE = re.compile(r"^(?P<region>.+?)(?P<grade>\d+)#(?:汽油|柴油)$")
_NOTICE_TIME_RE = re.compile(r"下次油价(\d{1,2})月(\d{1,2})日(\d{1,2})时调整")
_NOTICE_FORECAST_RE = re.compile(r"预计(上调|上涨|下调|下跌|不变|维持)")


class ParseError(Exception):
    """Raised when a page does not contain the expected data."""


def empty_prices():
    return {key: None for key in GRADE_KEYS.values()}


def parse_city_prices(html):
    """Return the four current prices for one city page.

    Invalid individual prices remain None and produce warnings.
    Raises ParseError when no price block or supported price labels are present.
    """
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one("#youjia")
    if block is None:
        raise ParseError("price block #youjia not found")

    prices = empty_prices()
    found = 0
    for dl in block.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if dt is None:
            logger.warning("Price entry has no label; skipping entry")
            continue
        match = _LABEL_RE.match(dt.get_text(strip=True))
        if match is None:
            logger.warning("Unrecognised price label: %r", dt.get_text(strip=True))
            continue
        key = GRADE_KEYS.get(match.group("grade"))
        if key is None:
            logger.warning("Unknown grade in label: %r", dt.get_text(strip=True))
            continue
        found += 1
        prices[key] = None
        if dd is None:
            logger.warning("Missing price for %s; storing null", key)
            continue
        try:
            value = float(dd.get_text(strip=True))
        except ValueError:
            logger.warning("Invalid price for %s: %r; storing null", key, dd.get_text(strip=True))
            continue
        if not math.isfinite(value) or value <= 0:
            logger.warning("Non-positive or non-finite price for %s: %r; storing null", key, value)
            continue
        prices[key] = value

    if found == 0:
        raise ParseError("no prices found in #youjia")
    return prices


def parse_notice(html, now):
    """Return (next_forecast, next_adjustment_at) from the adjustment notice.

    Either value may be None when the notice is missing or ambiguous.
    The year is inferred as the candidate closest to `now`, within 45 days.
    A time of 24时 is treated as 00:00 on the following day.
    """
    text = BeautifulSoup(html, "html.parser").get_text()

    forecast = None
    forecast_match = _NOTICE_FORECAST_RE.search(text)
    if forecast_match:
        forecast = FORECAST_KEYS[forecast_match.group(1)]

    adjustment_at = None
    time_match = _NOTICE_TIME_RE.search(text)
    if time_match:
        month, day, hour = (int(g) for g in time_match.groups())
        adjustment_at = _infer_adjustment_time(month, day, hour, now)

    return forecast, adjustment_at


_CHANGE_RANGE_RE = re.compile(r"预计(?:上调|上涨|下调|下跌)[^(（]*[(（]([^)）]*)[)）]")
_PER_LITER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*元/升")


def parse_max_change_per_liter(html):
    """Return the largest per-liter change in the notice, or None.

    Only the bracketed range after 预计上调/下调 is used, e.g. "0.07元/升-0.08元/升" -> 0.08.
    """
    text = BeautifulSoup(html, "html.parser").get_text()
    match = _CHANGE_RANGE_RE.search(text)
    if match is None:
        return None
    values = [float(v) for v in _PER_LITER_RE.findall(match.group(1))]
    return max(values) if values else None


def estimate_next_prices(current, forecast, change, adjustment_at, now):
    """Estimate next prices as current + max per-liter change (spec section 8).

    Returns all-None prices unless direction is up/down, the change is known,
    and the adjustment time is still in the future.
    """
    if change is None or forecast not in ("up", "down") or adjustment_at is None:
        return empty_prices()
    if datetime.fromisoformat(adjustment_at) <= now:
        return empty_prices()
    delta = change if forecast == "up" else -change
    return {
        key: (round(value + delta, 2) if value is not None else None)
        for key, value in current.items()
    }


def _infer_adjustment_time(month, day, hour, now):
    if not 0 <= hour <= 24:
        return None
    best = None
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            base = datetime(year, month, day, tzinfo=BEIJING_TZ)
        except ValueError:
            continue
        candidate = base + timedelta(hours=hour)
        distance = abs(candidate - now)
        if distance <= MAX_ADJUSTMENT_DISTANCE and (best is None or distance < best[0]):
            best = (distance, candidate)
    if best is None:
        return None
    return best[1].isoformat()
