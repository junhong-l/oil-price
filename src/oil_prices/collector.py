"""Collect city oil prices for configured provinces and write JSON data files."""

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .fetcher import FatalFetchError, FetchError, fetch_html
from .parser import (
    BEIJING_TZ,
    ParseError,
    empty_prices,
    estimate_next_prices,
    parse_city_prices,
    parse_max_change_per_liter,
    parse_notice,
)

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_FAILED = 2
REQUEST_DELAY_SECONDS = 2.0
REQUEST_JITTER_SECONDS = 1.0


def load_json(path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def iso(now):
    return now.astimezone(BEIJING_TZ).isoformat()


def collect_province(province_cfg, data_dir, now, session, sleep, delay):
    """Return (payload, city_status, all_ok, province_page_ok)."""
    code = province_cfg["province_code"]
    previous = load_json(data_dir / "provinces" / f"{code}.json") or {}
    previous_cities = {c["city_code"]: c for c in previous.get("cities", [])}

    all_ok = True
    province_page_ok = True
    province_error = None
    next_forecast = previous.get("next_forecast")
    next_adjustment_at = previous.get("next_adjustment_at")
    next_change = None
    sleep(delay + random.uniform(0, REQUEST_JITTER_SECONDS))
    try:
        province_html = fetch_html(session, province_cfg["province_source_url"], sleep=sleep)
        next_forecast, next_adjustment_at = parse_notice(province_html, now)
        next_change = parse_max_change_per_liter(province_html)
    except FatalFetchError:
        raise
    except (FetchError, ParseError) as exc:
        all_ok = False
        province_page_ok = False
        province_error = str(exc)

    cities_out = []
    city_status = {}
    for city_cfg in sorted(province_cfg["cities"], key=lambda c: c["city_code"]):
        city_code = city_cfg["city_code"]
        attempt_at = iso(now)
        previous_city = previous_cities.get(city_code)
        sleep(delay + random.uniform(0, REQUEST_JITTER_SECONDS))
        try:
            html = fetch_html(session, city_cfg["source_url"], sleep=sleep)
            prices = parse_city_prices(html, city_cfg["source_region_name"])
        except FatalFetchError:
            raise
        except (FetchError, ParseError) as exc:
            all_ok = False
            old = previous_city or {}
            cities_out.append({
                "city_name": city_cfg["city_name"],
                "city_code": city_code,
                "source_url": city_cfg["source_url"],
                "current_prices": old.get("current_prices", empty_prices()),
                "next_prices": old.get("next_prices", empty_prices()),
            })
            city_status[city_code] = {
                "last_attempt_at": attempt_at,
                "last_success_at": None,
                "error": str(exc),
                "stale": previous_city is not None,
            }
            continue

        cities_out.append({
            "city_name": city_cfg["city_name"],
            "city_code": city_code,
            "source_url": city_cfg["source_url"],
            "current_prices": prices,
            "next_prices": estimate_next_prices(
                prices, next_forecast, next_change, next_adjustment_at, now,
            ),
        })
        city_status[city_code] = {
            "last_attempt_at": attempt_at,
            "last_success_at": attempt_at,
            "error": None,
            "stale": False,
        }

    payload = {
        "province": province_cfg["province"],
        "province_code": code,
        "currency": "CNY",
        "uniform_pricing": False,
        "cities": cities_out,
        "next_forecast": next_forecast,
        "next_adjustment_at": next_adjustment_at,
        "fetched_at": iso(now) if all_ok else previous.get("fetched_at"),
    }
    if province_error:
        city_status["__province__"] = {
            "last_attempt_at": iso(now),
            "last_success_at": None,
            "error": province_error,
            "stale": True,
        }
    return payload, city_status, all_ok, province_page_ok


def collect_uniform_province(province_cfg, data_dir, now, session, sleep, delay):
    """Fetch only the province page for a province with one price for all cities.

    Return (payload, city_status, all_ok, province_page_ok) like collect_province.
    """
    code = province_cfg["province_code"]
    previous = load_json(data_dir / "provinces" / f"{code}.json") or {}
    attempt_at = iso(now)
    sleep(delay + random.uniform(0, REQUEST_JITTER_SECONDS))
    try:
        html = fetch_html(session, province_cfg["province_source_url"], sleep=sleep)
        prices = parse_city_prices(html, province_cfg["source_region_name"])
        next_forecast, next_adjustment_at = parse_notice(html, now)
        next_change = parse_max_change_per_liter(html)
        next_prices = estimate_next_prices(prices, next_forecast, next_change, next_adjustment_at, now)
        error = None
    except FatalFetchError:
        raise
    except (FetchError, ParseError) as exc:
        error = str(exc)
        prices = previous.get("current_prices", empty_prices())
        next_prices = previous.get("next_prices", empty_prices())
        next_forecast = previous.get("next_forecast")
        next_adjustment_at = previous.get("next_adjustment_at")

    city_status = {}
    for city_cfg in province_cfg["cities"]:
        city_status[city_cfg["city_code"]] = {
            "last_attempt_at": attempt_at,
            "last_success_at": None if error else attempt_at,
            "error": error,
            "stale": error is not None and bool(previous),
        }

    payload = {
        "province": province_cfg["province"],
        "province_code": code,
        "currency": "CNY",
        "uniform_pricing": True,
        "current_prices": prices,
        "next_prices": next_prices,
        "cities": [],
        "next_forecast": next_forecast,
        "next_adjustment_at": next_adjustment_at,
        "fetched_at": iso(now) if error is None else previous.get("fetched_at"),
    }
    return payload, city_status, error is None, error is None


def run(config_path, data_dir, now=None, session=None, sleep=time.sleep,
        delay=REQUEST_DELAY_SECONDS, province_code=None):
    now = now or datetime.now(timezone.utc)
    data_dir = Path(data_dir)
    session = session or requests.Session()
    config = load_json(Path(config_path))
    provinces = [
        p for p in config["provinces"]
        if province_code is None or p["province_code"] == province_code
    ]

    started_at = iso(now)
    previous_status = load_json(data_dir / "status.json") or {}
    regions_status = {}
    index_entries = []
    any_failure = False
    any_success = False
    fatal_error = None

    for province_cfg in provinces:
        collect = collect_uniform_province if province_cfg.get("uniform_pricing") else collect_province
        try:
            payload, status, all_ok, province_page_ok = collect(
                province_cfg, data_dir, now, session, sleep, delay,
            )
        except FatalFetchError as exc:
            fatal_error = str(exc)
            break

        write_json_atomic(data_dir / "provinces" / f"{payload['province_code']}.json", payload)

        configured_codes = [c["city_code"] for c in province_cfg["cities"]]
        successful = []
        missing = []
        for code in configured_codes:
            entry = status.get(code)
            prior = previous_status.get("regions", {}).get(code, {})
            if entry is None:
                entry = {"last_attempt_at": None, "last_success_at": None, "error": None, "stale": False}
            last_success = entry["last_success_at"] or prior.get("last_success_at")
            regions_status[code] = {
                "province_code": payload["province_code"],
                "last_attempt_at": entry["last_attempt_at"],
                "last_success_at": last_success,
                "error": entry["error"],
                "stale": entry["stale"],
            }
            if entry["error"] is None:
                successful.append(code)
            else:
                missing.append(code)
        if not all_ok:
            any_failure = True
        if successful:
            any_success = True

        index_entries.append({
            "province_code": payload["province_code"],
            "province": payload["province"],
            "uniform_pricing": payload["uniform_pricing"],
            "path": f"provinces/{payload['province_code']}.json",
            "expected_cities": len(configured_codes),
            "successful_cities": len(successful),
            "missing_cities": missing,
            "province_page_ok": province_page_ok,
        })

    if fatal_error:
        overall = "failed"
    elif not any_failure:
        overall = "success"
    elif any_success:
        overall = "partial"
    else:
        overall = "failed"

    finished_at = iso(datetime.now(timezone.utc))
    write_json_atomic(data_dir / "status.json", {
        "run_started_at": started_at,
        "run_finished_at": finished_at,
        "overall_status": overall,
        "fatal_error": fatal_error,
        "regions": regions_status,
    })
    write_json_atomic(data_dir / "index.json", {
        "generated_at": finished_at,
        "configured_provinces_complete": overall == "success" and fatal_error is None,
        "provinces": index_entries,
    })

    if fatal_error or overall == "failed":
        return EXIT_FAILED
    if overall == "partial":
        return EXIT_PARTIAL
    return EXIT_OK
