from __future__ import annotations

import io
import json
from pathlib import Path

import httpx

from confluence_fetch.fetcher import (
    FetchContext,
    build_comment_tree,
    build_document_markdown,
    build_auth_headers,
    default_assets_dir,
    emit_result,
    fetch_cloud_id,
    gateway_base_url,
    limit_roots,
    normalize_page_html,
    resolve_target,
)
from confluence_fetch.models import AssetsResult, DiscussionResult, FetchOptions, PageResult
from confluence_fetch.urls import resolve_target_without_redirects


def make_options(tmp_path: Path, *, format_name: str = "markdown") -> FetchOptions:
    return FetchOptions(
        token_env_name="CONFLUENCE_TOKEN",
        auth_email="user@example.com",
        format_name=format_name,
        output_path=None,
        download_images=False,
        assets_dir=None,
        comments=False,
        comment_limit=10,
        comment_kinds="all",
        verbose=False,
        no_progress=True,
    )


def test_resolve_target_without_redirects_uses_url_host_and_page_id() -> None:
    target = resolve_target_without_redirects(
        "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example"
    )

    assert target.host == "example.atlassian.net"
    assert target.site_url == "https://example.atlassian.net"
    assert target.page_id == "123456789"


def test_resolve_short_url_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wiki/x/AbCdEf":
            return httpx.Response(
                302,
                request=request,
                headers={"Location": "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example"},
            )
        return httpx.Response(200, request=request, text="ok")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=True)
    ctx = FetchContext(client=client, stderr=io.StringIO(), verbose=False, no_progress=True)

    target = resolve_target("https://example.atlassian.net/wiki/x/AbCdEf", client, ctx)

    assert target.page_id == "123456789"
    assert target.canonical_url.endswith("/123456789/Example")


def test_resolve_short_url_accepts_page_urls_with_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wiki/x/AQAtl":
            return httpx.Response(
                302,
                request=request,
                headers={
                    "Location": (
                        "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789"
                        "?atlOrigin=eyJpIjoiZmFrZSJ9"
                    )
                },
            )
        return httpx.Response(200, request=request, text="ok")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=True)
    ctx = FetchContext(client=client, stderr=io.StringIO(), verbose=False, no_progress=True)

    target = resolve_target("https://example.atlassian.net/wiki/x/AQAtl", client, ctx)

    assert target.page_id == "123456789"
    assert target.canonical_url.endswith("/123456789?atlOrigin=eyJpIjoiZmFrZSJ9")


def test_resolve_short_url_falls_back_to_api_when_redirect_goes_to_login() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wiki/x/AQAtl":
            return httpx.Response(
                302,
                request=request,
                headers={"Location": "https://example.atlassian.net/login?application=confluence&dest-url=%2Fwiki%2Fx%2FAQAtl"},
            )
        if request.url.path == "/login":
            return httpx.Response(200, request=request, text="login")
        if request.url.host == "api.atlassian.com" and request.url.path == "/ex/confluence/cloud-id/wiki/api/v2/pages":
            return httpx.Response(
                200,
                request=request,
                json={
                    "results": [
                        {
                            "id": "123456789",
                            "_links": {
                                "tinyui": "/x/AQAtl",
                                "webui": "/spaces/ENG/pages/123456789/Example",
                            },
                        }
                    ],
                    "_links": {},
                },
            )
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=True)
    ctx = FetchContext(client=client, stderr=io.StringIO(), verbose=False, no_progress=True)

    target = resolve_target(
        "https://example.atlassian.net/wiki/x/AQAtl",
        client,
        ctx,
        gateway_base="https://api.atlassian.com/ex/confluence/cloud-id/wiki",
    )

    assert target.page_id == "123456789"
    assert target.canonical_url == "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example"


def test_comment_tree_and_limit_behavior() -> None:
    raw_comments = [
        {
            "id": "1",
            "body": {"view": {"value": "<p>Oldest footer</p>"}},
            "history": {"createdBy": {"displayName": "A"}, "createdDate": "2024-01-01T00:00:00Z"},
        },
        {
            "id": "2",
            "body": {"view": {"value": "<p>Newest footer</p>"}},
            "history": {"createdBy": {"displayName": "B"}, "createdDate": "2024-01-02T00:00:00Z"},
        },
        {
            "id": "3",
            "body": {"view": {"value": "<p>Inline</p>"}},
            "history": {"createdBy": {"displayName": "C"}, "createdDate": "2024-01-03T00:00:00Z"},
            "extensions": {"inlineProperties": {"text": "selection"}},
        },
    ]

    footer, inline = build_comment_tree(
        raw_comments,
        canonical_url="https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
    )

    assert [node.id for node in limit_roots(footer, 1)] == ["2"]
    assert [node.id for node in inline] == ["3"]
    assert inline[0].context == "selection"


def test_normalize_page_html_makes_relative_links_absolute() -> None:
    html = '<p><a href="/wiki/spaces/ENG/pages/123">Page</a><img src="/wiki/download/image.png"/></p>'
    normalized = normalize_page_html(
        html,
        "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
    )

    assert 'href="https://example.atlassian.net/wiki/spaces/ENG/pages/123"' in normalized
    assert 'src="https://example.atlassian.net/wiki/download/image.png"' in normalized


def test_default_assets_dir_is_deterministic(tmp_path: Path) -> None:
    output_path = tmp_path / "page.md"
    assert default_assets_dir(output_path, "123").name == "page.assets"
    assert default_assets_dir(None, "123").name == "123.assets"


def test_fetch_cloud_id_and_gateway_base() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, request=request, json={"cloudId": "11111111-2222-3333-4444-555555555555"})
    )
    client = httpx.Client(transport=transport, follow_redirects=True)
    ctx = FetchContext(client=client, stderr=io.StringIO(), verbose=False, no_progress=True)

    cloud_id = fetch_cloud_id("https://example.atlassian.net", client, ctx)

    assert cloud_id == "11111111-2222-3333-4444-555555555555"
    assert gateway_base_url(cloud_id) == "https://api.atlassian.com/ex/confluence/11111111-2222-3333-4444-555555555555/wiki"


def test_build_auth_headers_uses_basic_auth() -> None:
    basic_headers = build_auth_headers("token-123", "user@example.com")

    assert basic_headers["Authorization"].startswith("Basic ")


def test_emit_result_supports_markdown_and_json(tmp_path: Path) -> None:
    result = PageResult(
        page_id="123",
        title="Example",
        url="https://example.atlassian.net/wiki/spaces/ENG/pages/123/Example",
        site="https://example.atlassian.net",
        body_markdown="Hello",
        document_markdown="# 123 Example\n\n# Page\nHello",
        discussion=DiscussionResult(included=False, markdown=None),
        assets=AssetsResult(downloaded=False, directory=None, files=[]),
    )

    markdown_buffer = io.StringIO()
    emit_result(result, make_options(tmp_path, format_name="markdown"), markdown_buffer)
    assert markdown_buffer.getvalue().startswith("# 123 Example")

    json_buffer = io.StringIO()
    emit_result(result, make_options(tmp_path, format_name="json"), json_buffer)
    payload = json.loads(json_buffer.getvalue())
    assert payload["content"]["document_markdown"].startswith("# 123 Example")


def test_build_document_markdown_includes_discussion_only_when_requested() -> None:
    without_discussion = build_document_markdown("123", "Example", "Body", None)
    with_discussion = build_document_markdown("123", "Example", "Body", "Comments")

    assert "# Discussion" not in without_discussion
    assert "# Discussion" in with_discussion
