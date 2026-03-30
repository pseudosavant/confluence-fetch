from __future__ import annotations

import re
from urllib.parse import urlparse

from confluence_fetch.errors import UsageError
from confluence_fetch.models import ResolvedTarget


PAGE_ID_PATTERNS = [
    re.compile(r"/wiki/spaces/[^/]+/pages/(?P<page_id>\d+)(?:[/?#]|$)"),
    re.compile(r"/wiki/pages/viewpage\.action\?pageId=(?P<page_id>\d+)"),
]
SHORT_URL_PATTERN = re.compile(r"/wiki/x/[^/?#]+/?$")


def parse_host(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise UsageError("fetch requires a full Confluence URL.")
    return parsed.netloc


def site_url_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise UsageError("fetch requires a full Confluence URL.")
    return f"{parsed.scheme}://{parsed.netloc}"


def extract_page_id(url: str) -> str | None:
    for pattern in PAGE_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group("page_id")
    return None


def is_short_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(SHORT_URL_PATTERN.match(parsed.path))


def extract_short_path(url: str) -> str | None:
    parsed = urlparse(url)
    if not SHORT_URL_PATTERN.match(parsed.path):
        return None
    if parsed.path.startswith("/wiki/"):
        return parsed.path[len("/wiki") :]
    return parsed.path


def resolve_target_without_redirects(url: str) -> ResolvedTarget:
    host = parse_host(url)
    site_url = site_url_from_url(url)
    page_id = extract_page_id(url)
    if not page_id:
        raise UsageError(
            "Could not derive a page ID from the URL. Use a full Confluence page URL or a short /wiki/x/ URL."
        )
    return ResolvedTarget(
        requested_url=url,
        canonical_url=url,
        site_url=site_url,
        host=host,
        page_id=page_id,
    )
