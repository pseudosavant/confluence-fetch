from __future__ import annotations

import json
import mimetypes
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from confluence_fetch.errors import AppError, AuthError, NotFoundError, RateLimitError, UsageError
from confluence_fetch.markdown import (
    collect_image_sources,
    markdown_from_html,
    normalize_html_links,
    relative_markdown_path,
    rewrite_image_sources,
    tidy_markdown,
)
from confluence_fetch.models import (
    AssetFile,
    AssetsResult,
    CommentNode,
    DiscussionResult,
    FetchOptions,
    PageResult,
    ResolvedTarget,
)
from confluence_fetch.urls import (
    extract_page_id,
    extract_short_path,
    is_short_url,
    parse_host,
    resolve_target_without_redirects,
    site_url_from_url,
)


MAX_RETRIES = 4


import base64


def build_auth_headers(token: str, email: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "confluence-fetch/0.12.0",
    }
    raw = f"{email}:{token}".encode("utf-8")
    headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
    return headers


@dataclass(slots=True)
class FetchContext:
    client: httpx.Client
    stderr: Any
    verbose: bool
    no_progress: bool

    def log(self, message: str) -> None:
        if self.verbose:
            self.stderr.write(f"{message}\n")
            self.stderr.flush()

    def progress(self, message: str) -> None:
        if not self.no_progress:
            self.stderr.write(f"{message}\n")
            self.stderr.flush()


def request(client: httpx.Client, method: str, url: str, *, ctx: FetchContext) -> httpx.Response:
    last_response: httpx.Response | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.request(method, url)
        except httpx.HTTPError as exc:
            if attempt == MAX_RETRIES:
                raise AppError(f"HTTP request failed: {exc}") from exc
            time.sleep(0.5 * attempt)
            continue

        last_response = response
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if attempt == MAX_RETRIES:
                raise RateLimitError("Rate limited after retries.")
            sleep_for = float(retry_after) if retry_after and retry_after.isdigit() else 0.5 * attempt
            ctx.log(f"Rate limited. Retrying in {sleep_for} seconds.")
            time.sleep(sleep_for)
            continue

        if response.status_code in {500, 502, 503, 504} and attempt < MAX_RETRIES:
            time.sleep(0.5 * attempt)
            continue

        if response.status_code in {401, 403}:
            raise AuthError("Authentication failed. Check the resolved token environment variable.")
        if response.status_code == 404:
            raise NotFoundError("The requested Confluence page was not found.")
        if response.status_code >= 400:
            raise AppError(f"Request failed with status {response.status_code}: {response.text}")
        return response

    if last_response is not None and last_response.status_code == 429:
        raise RateLimitError("Rate limited after retries.")
    raise AppError("Request failed after retries.")


def fetch_cloud_id(site_url: str, client: httpx.Client, ctx: FetchContext) -> str:
    ctx.progress("Resolving cloudId...")
    response = request(client, "GET", f"{site_url.rstrip('/')}/_edge/tenant_info", ctx=ctx)
    payload = response.json()
    cloud_id = payload.get("cloudId")
    if not isinstance(cloud_id, str) or not cloud_id.strip():
        raise AppError("tenant_info response did not include a cloudId.")
    return cloud_id.strip()


def gateway_base_url(cloud_id: str) -> str:
    return f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki"


def resolve_short_url_via_api(
    url: str,
    *,
    site_url: str,
    gateway_base: str,
    client: httpx.Client,
    ctx: FetchContext,
) -> ResolvedTarget:
    short_path = extract_short_path(url)
    if not short_path:
        raise UsageError("The URL is not a supported Confluence short URL.")

    ctx.progress("Resolving short URL via API...")
    page_url = f"{gateway_base}/api/v2/pages?limit=250"
    while page_url:
        response = request(client, "GET", page_url, ctx=ctx)
        payload = response.json()
        page_results = payload.get("results", [])
        if not isinstance(page_results, list):
            raise AppError("Confluence API returned invalid results.")
        for item in page_results:
            if not isinstance(item, dict):
                continue
            links = item.get("_links", {})
            tinyui = links.get("tinyui") if isinstance(links, dict) else None
            if tinyui != short_path:
                continue
            page_id = str(item.get("id", "")).strip()
            webui = links.get("webui") if isinstance(links, dict) else None
            canonical_url = (
                f"{site_url}/wiki{webui}"
                if isinstance(webui, str) and webui.startswith("/")
                else f"{site_url}{short_path}"
            )
            if not page_id:
                raise AppError("Confluence API returned a short-link match without a page ID.")
            return ResolvedTarget(
                requested_url=url,
                canonical_url=canonical_url,
                site_url=site_url,
                host=parse_host(site_url),
                page_id=page_id,
            )
        page_url = resolve_next_url(gateway_base, payload.get("_links", {}).get("next"))

    raise UsageError("The short URL did not resolve to a Confluence page URL with a page ID.")


def resolve_target(url: str, client: httpx.Client, ctx: FetchContext, gateway_base: str | None = None) -> ResolvedTarget:
    if not is_short_url(url):
        return resolve_target_without_redirects(url)

    ctx.progress("Resolving short URL...")
    response = request(client, "GET", url, ctx=ctx)
    canonical_url = str(response.url)
    page_id = extract_page_id(canonical_url)
    if page_id:
        return ResolvedTarget(
            requested_url=url,
            canonical_url=canonical_url,
            site_url=site_url_from_url(canonical_url),
            host=parse_host(canonical_url),
            page_id=page_id,
        )
    if gateway_base is None:
        raise UsageError("The short URL did not resolve to a Confluence page URL with a page ID.")
    return resolve_short_url_via_api(
        url,
        site_url=site_url_from_url(url),
        gateway_base=gateway_base,
        client=client,
        ctx=ctx,
    )


def extract_body_html(payload: dict[str, Any]) -> str:
    body = payload.get("body")
    if isinstance(body, dict):
        for key in ("export_view", "view", "storage", "styled_view"):
            section = body.get(key)
            if isinstance(section, dict) and isinstance(section.get("value"), str):
                return section["value"]
            if isinstance(section, str):
                return section
        if isinstance(body.get("value"), str):
            return body["value"]
    for key in ("body", "renderedBody", "value"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def fetch_page_payload(
    target: ResolvedTarget,
    gateway_base: str,
    client: httpx.Client,
    ctx: FetchContext,
) -> dict[str, Any]:
    ctx.progress("Fetching page...")
    candidates = [
        f"{gateway_base}/api/v2/pages/{target.page_id}?body-format=export_view",
        f"{gateway_base}/api/v2/pages/{target.page_id}?body-format=view",
        f"{gateway_base}/api/v2/pages/{target.page_id}?body-format=storage",
        f"{gateway_base}/api/v2/pages/{target.page_id}",
    ]
    last_error: AppError | None = None
    for page_url in candidates:
        try:
            response = request(client, "GET", page_url, ctx=ctx)
        except NotFoundError as exc:
            last_error = exc
            continue
        payload = response.json()
        payload["_requested_url"] = page_url
        return payload
    if last_error is not None:
        raise last_error
    raise AppError("Unable to fetch page.")


def resolve_next_url(base_url: str, next_link: Any) -> str:
    if not isinstance(next_link, str) or not next_link.strip():
        return ""
    next_url = next_link.strip()
    if next_url.startswith("http://") or next_url.startswith("https://"):
        return next_url
    if next_url.startswith("/wiki/"):
        next_url = next_url[len("/wiki") :]
    if not next_url.startswith("/"):
        next_url = f"/{next_url}"
    return f"{base_url.rstrip('/')}{next_url}"


def fetch_paginated_results(
    initial_url: str,
    *,
    base_url: str,
    client: httpx.Client,
    ctx: FetchContext,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor_url = initial_url
    while cursor_url:
        response = request(client, "GET", cursor_url, ctx=ctx)
        payload = response.json()
        page_results = payload.get("results", [])
        if not isinstance(page_results, list):
            raise AppError("Confluence API returned invalid results.")
        results.extend(item for item in page_results if isinstance(item, dict))
        cursor_url = resolve_next_url(base_url, payload.get("_links", {}).get("next"))
    return results


def fetch_comment_children(
    comment_kind: str,
    comment_id: str,
    *,
    gateway_base: str,
    client: httpx.Client,
    ctx: FetchContext,
) -> list[dict[str, Any]]:
    child_url = (
        f"{gateway_base}/api/v2/{comment_kind}/{comment_id}/children"
        "?body-format=storage&status=current&limit=250"
    )
    children = fetch_paginated_results(child_url, base_url=gateway_base, client=client, ctx=ctx)
    ordered = sorted(children, key=comment_sort_key)
    for child in ordered:
        child_id = str(child.get("id", "")).strip()
        if child_id:
            child["_children"] = fetch_comment_children(
                comment_kind,
                child_id,
                gateway_base=gateway_base,
                client=client,
                ctx=ctx,
            )
    return ordered


def comment_sort_key(payload: dict[str, Any]) -> tuple[str, str]:
    created_at = parse_comment_created_at(payload) or ""
    comment_id = str(payload.get("id", "")).strip()
    return (created_at, comment_id)


def select_root_comments(comments: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(comments, key=comment_sort_key)
    if len(ordered) <= limit:
        return ordered
    return ordered[-limit:]


def fetch_comments_payload(
    target: ResolvedTarget,
    gateway_base: str,
    *,
    comment_limit: int,
    comment_kinds: str,
    client: httpx.Client,
    ctx: FetchContext,
) -> list[dict[str, Any]]:
    ctx.progress("Fetching comments...")
    comments: list[dict[str, Any]] = []
    kinds: list[tuple[str, str, str]] = []
    if comment_kinds in {"all", "footer"}:
        kinds.append(("footer-comments", "footer-comments", "footer"))
    if comment_kinds in {"all", "inline"}:
        kinds.append(("inline-comments", "inline-comments", "inline"))

    for endpoint_name, comment_kind, location in kinds:
        root_url = (
            f"{gateway_base}/api/v2/pages/{target.page_id}/{endpoint_name}"
            "?body-format=storage&status=current&limit=250"
        )
        roots = select_root_comments(
            fetch_paginated_results(root_url, base_url=gateway_base, client=client, ctx=ctx),
            comment_limit,
        )
        for root in roots:
            root_id = str(root.get("id", "")).strip()
            root.setdefault("extensions", {})
            root["extensions"]["location"] = "inline" if location == "inline" else "footer"
            if root_id:
                root["_children"] = fetch_comment_children(
                    comment_kind,
                    root_id,
                    gateway_base=gateway_base,
                    client=client,
                    ctx=ctx,
                )
            comments.append(root)
    return comments


def normalize_page_html(html: str, canonical_url: str) -> str:
    base_url = canonical_url if canonical_url.endswith("/") else f"{canonical_url}/"
    return normalize_html_links(html, base_url)


def default_assets_dir(output_path: Path | None, page_id: str) -> Path:
    if output_path is not None:
        return output_path.with_name(f"{output_path.stem}.assets")
    return Path.cwd() / f"{page_id}.assets"


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return cleaned or "asset"


def download_assets(
    html: str,
    *,
    assets_dir: Path,
    client: httpx.Client,
    ctx: FetchContext,
    output_path: Path | None,
) -> tuple[str, AssetsResult]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    sources = collect_image_sources(html)
    replacements: dict[str, str] = {}
    files: list[AssetFile] = []
    base_dir = output_path.parent if output_path is not None else Path.cwd()

    for index, source_url in enumerate(sources, start=1):
        try:
            response = request(client, "GET", source_url, ctx=ctx)
            parsed = urlparse(source_url)
            ext = Path(parsed.path).suffix
            if not ext:
                content_type = response.headers.get("Content-Type", "").split(";")[0]
                ext = mimetypes.guess_extension(content_type) or ".bin"
            filename = sanitize_filename(f"{index:03d}-{Path(parsed.path).stem or 'image'}{ext}")
            asset_path = assets_dir / filename
            asset_path.write_bytes(response.content)
            markdown_ref = relative_markdown_path(asset_path, base_dir)
            replacements[source_url] = markdown_ref
            files.append(AssetFile(source_url=source_url, path=str(asset_path), downloaded=True))
        except AppError as exc:
            ctx.log(f"Asset download failed for {source_url}: {exc}")
            files.append(AssetFile(source_url=source_url, path="", downloaded=False))

    rewritten_html = rewrite_image_sources(html, replacements)
    return rewritten_html, AssetsResult(downloaded=bool(sources), directory=str(assets_dir), files=files)


def parse_comment_kind(raw: dict[str, Any]) -> str:
    extensions = raw.get("extensions", {})
    if extensions.get("location") == "inline":
        return "inline"
    if extensions.get("inlineProperties"):
        return "inline"
    return "footer"


def parse_comment_parent_id(raw: dict[str, Any], page_id: str) -> str | None:
    extensions = raw.get("extensions", {})
    parent_id = extensions.get("parentId")
    if isinstance(parent_id, str) and parent_id and parent_id != page_id:
        return parent_id
    ancestors = raw.get("ancestors", [])
    if ancestors:
        ancestor_id = ancestors[-1].get("id")
        if ancestor_id and ancestor_id != page_id:
            return str(ancestor_id)
    return None


def parse_comment_context(raw: dict[str, Any]) -> str | None:
    inline = raw.get("extensions", {}).get("inlineProperties", {})
    if not isinstance(inline, dict):
        return None
    for key in ("text", "selection", "originalSelection"):
        value = inline.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_comment_author(raw: dict[str, Any]) -> str:
    candidates = [
        raw.get("author", {}),
        raw.get("history", {}).get("createdBy", {}),
        raw.get("version", {}).get("by", {}),
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("displayName", "publicName", "accountId"):
            value = candidate.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("authorId", "ownerId", "creatorId"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            return value
    return "Unknown author"


def parse_comment_created_at(raw: dict[str, Any]) -> str | None:
    for value in (
        raw.get("version", {}).get("createdAt"),
        raw.get("history", {}).get("createdDate"),
        raw.get("version", {}).get("when"),
        raw.get("createdDate"),
    ):
        if isinstance(value, str) and value:
            return value
    return None


def parse_comment_body_markdown(raw: dict[str, Any], canonical_url: str) -> str:
    html = extract_body_html(raw)
    return markdown_from_html(normalize_page_html(html, canonical_url))


def build_comment_tree(
    raw_comments: list[dict[str, Any]],
    *,
    canonical_url: str,
) -> tuple[list[CommentNode], list[CommentNode]]:
    def build_nodes(raw_items: list[dict[str, Any]], kind: str) -> list[CommentNode]:
        nodes: list[CommentNode] = []
        for raw in raw_items:
            raw.setdefault("extensions", {})
            raw["extensions"]["location"] = kind
            node = CommentNode(
                id=str(raw.get("id", "")),
                kind=kind,
                author=parse_comment_author(raw),
                created_at=parse_comment_created_at(raw),
                body_markdown=parse_comment_body_markdown(raw, canonical_url),
                context=parse_comment_context(raw),
                parent_id=None,
            )
            children = raw.get("_children", [])
            if isinstance(children, list):
                node.replies = build_nodes([child for child in children if isinstance(child, dict)], kind)
            nodes.append(node)
        return sorted(nodes, key=lambda node: (node.created_at or "", node.id))

    footer_raw = [raw for raw in raw_comments if parse_comment_kind(raw) == "footer"]
    inline_raw = [raw for raw in raw_comments if parse_comment_kind(raw) == "inline"]
    return build_nodes(footer_raw, "footer"), build_nodes(inline_raw, "inline")


def limit_roots(roots: list[CommentNode], limit: int) -> list[CommentNode]:
    if len(roots) <= limit:
        return roots
    return roots[-limit:]


def render_comment(node: CommentNode, level: int = 3) -> str:
    heading = "#" * min(level, 6)
    lines = [f"{heading} {node.author}"]
    if node.created_at:
        lines.append(f"Created: {node.created_at}")
    if node.context:
        lines.append(f"On: {node.context}")
    if node.body_markdown:
        lines.extend(["", node.body_markdown])
    for reply in node.replies:
        lines.extend(["", render_comment(reply, level + 1)])
    return "\n".join(lines)


def render_discussion(
    footer_roots: list[CommentNode],
    inline_roots: list[CommentNode],
    *,
    comment_kinds: str,
) -> str:
    sections: list[str] = []
    if comment_kinds in {"all", "footer"}:
        sections.append("## Footer Comments")
        sections.extend(render_comment(node) for node in footer_roots) if footer_roots else sections.append(
            "No footer comments."
        )
    if comment_kinds in {"all", "inline"}:
        sections.append("## Inline Comments")
        sections.extend(render_comment(node) for node in inline_roots) if inline_roots else sections.append(
            "No inline comments."
        )
    return tidy_markdown("\n\n".join(sections))


def build_document_markdown(page_id: str, title: str, body_markdown: str, discussion_markdown: str | None) -> str:
    parts = [f"# {page_id} {title}", "", "# Page", body_markdown or ""]
    if discussion_markdown is not None:
        parts.extend(["", "# Discussion", discussion_markdown])
    return tidy_markdown("\n".join(parts))


def fetch_document(
    target_url: str,
    options: FetchOptions,
    *,
    token: str,
    stdout: Any = sys.stdout,
    stderr: Any = sys.stderr,
    client: httpx.Client | None = None,
) -> PageResult:
    headers = build_auth_headers(token, options.auth_email)
    owned_client = client is None
    active_client = client or httpx.Client(headers=headers, follow_redirects=True, timeout=30.0)
    ctx = FetchContext(client=active_client, stderr=stderr, verbose=options.verbose, no_progress=options.no_progress)

    try:
        initial_site_url = site_url_from_url(target_url)
        cloud_id = fetch_cloud_id(initial_site_url, active_client, ctx)
        gateway_base = gateway_base_url(cloud_id)
        target = resolve_target(target_url, active_client, ctx, gateway_base=gateway_base)
        page_payload = fetch_page_payload(target, gateway_base, active_client, ctx)
        title = page_payload.get("title") or ""
        page_html = extract_body_html(page_payload)
        webui = page_payload.get("_links", {}).get("webui")
        canonical_url = (
            f"{target.site_url}{webui}" if isinstance(webui, str) and webui.startswith("/wiki/") else target.canonical_url
        )

        normalized_html = normalize_page_html(page_html, canonical_url)
        assets = AssetsResult(downloaded=False, directory=None, files=[])
        if options.download_images:
            assets_dir = options.assets_dir or default_assets_dir(options.output_path, target.page_id)
            normalized_html, assets = download_assets(
                normalized_html,
                assets_dir=assets_dir,
                client=active_client,
                ctx=ctx,
                output_path=options.output_path,
            )

        body_markdown = markdown_from_html(normalized_html)
        discussion = DiscussionResult(included=options.comments, markdown=None)
        if options.comments:
            raw_comments = fetch_comments_payload(
                target,
                gateway_base,
                comment_limit=options.comment_limit,
                comment_kinds=options.comment_kinds,
                client=active_client,
                ctx=ctx,
            )
            footer_roots, inline_roots = build_comment_tree(
                raw_comments,
                canonical_url=canonical_url,
            )
            discussion = DiscussionResult(
                included=True,
                markdown=render_discussion(footer_roots, inline_roots, comment_kinds=options.comment_kinds),
                footer_comments=footer_roots,
                inline_comments=inline_roots,
            )

        return PageResult(
            page_id=target.page_id,
            title=title,
            url=canonical_url,
            site=target.site_url,
            body_markdown=body_markdown,
            document_markdown=build_document_markdown(target.page_id, title, body_markdown, discussion.markdown),
            discussion=discussion,
            assets=assets,
        )
    finally:
        if owned_client:
            active_client.close()


def emit_result(result: PageResult, options: FetchOptions, stdout: Any) -> None:
    if options.format_name == "json":
        payload = json.dumps(result.to_json_dict(), indent=2, ensure_ascii=False) + "\n"
    else:
        payload = result.document_markdown + "\n"

    if options.output_path is not None:
        options.output_path.parent.mkdir(parents=True, exist_ok=True)
        options.output_path.write_text(payload, encoding="utf-8", newline="\n")
        return

    stdout.write(payload)
    stdout.flush()
