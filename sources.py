"""Loading an OpenAPI spec from a FastAPI /docs URL."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests

DOCS_SEGMENTS = ("docs", "redoc")


class SpecFetchError(Exception):
    """Raised when the spec cannot be fetched or parsed."""


def _clean(raw: str) -> tuple[str, str]:
    """Normalise user input -> (url without query/fragment, last path segment)."""
    raw = raw.strip()
    if not raw:
        raise ValueError("Enter your FastAPI docs URL, e.g. https://host/docs")
    if "://" not in raw:
        local = raw.startswith(("localhost", "127.", "0.0.0.0"))
        raw = ("http://" if local else "https://") + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError("That doesn't look like a valid URL.")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")), path.rsplit("/", 1)[-1].lower()


def docs_to_openapi_url(raw: str) -> str:
    """`https://host/prefix/docs` -> `https://host/prefix/openapi.json`."""
    url, last = _clean(raw)
    if last in DOCS_SEGMENTS:
        return url[: -len(last)] + "openapi.json"
    if last == "openapi.json":
        return url
    raise ValueError("The URL must end with /docs (for example https://host/docs).")


def _get(url: str, accept: str = "application/json") -> requests.Response:
    try:
        res = requests.get(url, timeout=15, headers={"Accept": accept})
    except requests.exceptions.RequestException as e:
        raise SpecFetchError(f"Could not reach {url}: {e}") from e
    if res.status_code != 200:
        raise SpecFetchError(f"{url} returned HTTP {res.status_code}.")
    return res


def _get_json(url: str) -> dict:
    res = _get(url)
    try:
        return res.json()
    except ValueError as e:
        raise SpecFetchError(f"{url} did not return valid JSON.") from e


def _openapi_url_from_docs_page(docs_url: str) -> str | None:
    """Fallback for apps with a custom `openapi_url`: read it from the docs HTML."""
    html = _get(docs_url, "text/html").text
    for pattern in (r"""url\s*:\s*['"]([^'"]+)['"]""", r"""spec-url=['"]([^'"]+)['"]"""):
        m = re.search(pattern, html)
        if m:
            return urljoin(docs_url, m.group(1))
    return None


def fetch_openapi(raw_url: str) -> tuple[dict, str]:
    """Return (spec, resolved_openapi_url) for a FastAPI /docs URL."""
    openapi_url = docs_to_openapi_url(raw_url)
    try:
        return _get_json(openapi_url), openapi_url
    except SpecFetchError as first_error:
        docs_url, last = _clean(raw_url)
        if last not in DOCS_SEGMENTS:
            raise
        found = _openapi_url_from_docs_page(docs_url)
        if not found or found == openapi_url:
            raise first_error
        return _get_json(found), found
