from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import yaml
from yaml.nodes import MappingNode, ScalarNode

from confluence_fetch.errors import UsageError
from confluence_fetch.runtime import DISTRIBUTION_NAME


MANAGED_BY = DISTRIBUTION_NAME
MANAGED_MARKER = "<!-- managed-by: confluence-fetch -->"
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|$)", re.M | re.S)


@dataclass(frozen=True)
class SkillMetadata:
    manager_present: bool = False
    manager: str | None = None
    version: str | None = None
    hash_present: bool = False
    content_hash: str | None = None
    hash_span: tuple[int, int] | None = None


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _mapping(node: object) -> dict[str, tuple[ScalarNode, object]]:
    if not isinstance(node, MappingNode):
        raise UsageError("Skill front matter and metadata must be YAML mappings.")
    result = {}
    for key, value in node.value:
        if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str" or key.value in result:
            raise UsageError("Skill YAML contains ambiguous or duplicate keys.")
        result[key.value] = (key, value)
    return result


def _string(node: object) -> str | None:
    if isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:str":
        return node.value
    return None


def parse_metadata(text: str) -> SkillMetadata:
    """Parse YAML nodes to retain exact scalar offsets. Never serialize installed YAML."""
    text = normalize_newlines(text)
    match = _FRONT_MATTER.match(text)
    if match is None:
        if text.startswith("---"):
            raise UsageError("Skill YAML front matter has no closing delimiter.")
        return SkillMetadata()
    try:
        root = yaml.compose(match[1], Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise UsageError("Unable to parse skill YAML front matter.") from exc
    if root is None:
        return SkillMetadata()
    front = _mapping(root)
    if "metadata" not in front:
        return SkillMetadata()
    metadata = _mapping(front["metadata"][1])
    values = {key: _string(value) for key, (_, value) in metadata.items()}
    span = None
    if "managed-content-sha256" in metadata:
        key, value = metadata["managed-content-sha256"]
        # Aliases and block scalars do not have an unambiguous inline value to replace.
        if isinstance(value, ScalarNode) and value.style in (None, "'", '"'):
            if value.start_mark.index >= key.end_mark.index:
                offset = match.start(1)
                span = (offset + value.start_mark.index, offset + value.end_mark.index)
    return SkillMetadata(
        manager_present="managed-by" in metadata,
        manager=values.get("managed-by"),
        version=values.get("managed-version"),
        hash_present="managed-content-sha256" in metadata,
        content_hash=values.get("managed-content-sha256"),
        hash_span=span,
    )


def content_digest(text: str, metadata: SkillMetadata) -> str:
    text = normalize_newlines(text)
    if metadata.hash_span is None:
        raise ValueError("Skill hash has no scalar value span.")
    start, end = metadata.hash_span
    empty_hash_text = text[:start] + '""' + text[end:]
    return "sha256:" + hashlib.sha256(empty_hash_text.encode("utf-8")).hexdigest()


def integrity_state(text: str, metadata: SkillMetadata) -> str:
    if not metadata.hash_present:
        return "missing"
    if metadata.hash_span is None or not _HASH_PATTERN.fullmatch(metadata.content_hash or ""):
        return "malformed"
    return "valid" if content_digest(text, metadata) == metadata.content_hash else "altered"
