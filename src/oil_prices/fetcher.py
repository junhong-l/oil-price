"""HTTP fetching for qiyoujiage.com with host allowlist and stop rules."""

import time
from urllib.parse import urlparse

import requests

ALLOWED_HOSTS = {"www.qiyoujiage.com"}
TIMEOUT = (10, 30)
USER_AGENT = "Mozilla/5.0 (compatible; china-city-oil-prices/0.1)"
MAX_RETRIES = 2
BACKOFF_SECONDS = 5


class FetchError(Exception):
    """A single request failed; the caller may keep going with other regions."""


class FatalFetchError(FetchError):
    """The site refused us (403 or persistent 429); the whole run must stop."""


def check_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_HOSTS:
        raise FatalFetchError(f"URL host not allowed: {url}")


def fetch_html(session, url, sleep=time.sleep):
    check_url(url)
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                sleep(BACKOFF_SECONDS)
                continue
            raise FetchError(f"request failed for {url}: {exc}") from exc

        if response.status_code == 403:
            raise FatalFetchError(f"403 Forbidden for {url}")
        if response.status_code == 429:
            if attempt < MAX_RETRIES:
                sleep(BACKOFF_SECONDS * (attempt + 1))
                continue
            raise FatalFetchError(f"persistent 429 for {url}")
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code} for {url}")

        check_url(response.url)
        response.encoding = "utf-8"
        return response.text
    raise FetchError(f"no response for {url}")
