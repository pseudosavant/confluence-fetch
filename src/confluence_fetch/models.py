from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppConfig:
    default_token_env_var: str | None = None
    default_email: str | None = None
    domain_token_env_vars: dict[str, str] = field(default_factory=dict)
    domain_emails: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolvedTarget:
    requested_url: str
    canonical_url: str
    site_url: str
    host: str
    page_id: str


@dataclass(slots=True)
class CommentNode:
    id: str
    kind: str
    author: str
    created_at: str | None
    body_markdown: str
    context: str | None = None
    parent_id: str | None = None
    replies: list["CommentNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "author": self.author,
            "created_at": self.created_at,
            "body_markdown": self.body_markdown,
            "context": self.context,
            "parent_id": self.parent_id,
            "replies": [reply.to_dict() for reply in self.replies],
        }


@dataclass(slots=True)
class AssetFile:
    source_url: str
    path: str
    downloaded: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AssetsResult:
    downloaded: bool
    directory: str | None
    files: list[AssetFile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "downloaded": self.downloaded,
            "directory": self.directory,
            "files": [asset.to_dict() for asset in self.files],
        }


@dataclass(slots=True)
class DiscussionResult:
    included: bool
    markdown: str | None
    footer_comments: list[CommentNode] = field(default_factory=list)
    inline_comments: list[CommentNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "included": self.included,
            "markdown": self.markdown,
            "footer_comments": [comment.to_dict() for comment in self.footer_comments],
            "inline_comments": [comment.to_dict() for comment in self.inline_comments],
        }


@dataclass(slots=True)
class PageResult:
    page_id: str
    title: str
    url: str
    site: str
    body_markdown: str
    document_markdown: str
    discussion: DiscussionResult
    assets: AssetsResult

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "page": {
                "id": self.page_id,
                "title": self.title,
                "url": self.url,
                "site": self.site,
            },
            "content": {
                "body_markdown": self.body_markdown,
                "document_markdown": self.document_markdown,
            },
            "discussion": self.discussion.to_dict(),
            "assets": self.assets.to_dict(),
        }


@dataclass(slots=True)
class FetchOptions:
    token_env_name: str
    auth_email: str | None
    format_name: str
    output_path: Path | None
    download_images: bool
    assets_dir: Path | None
    comments: bool
    comment_limit: int
    comment_kinds: str
    verbose: bool
    no_progress: bool
