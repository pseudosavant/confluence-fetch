from __future__ import annotations

import json

from confluence_fetch.skill_metadata import MANAGED_BY, content_digest, parse_metadata


_SKILL_TEMPLATE = """---
name: confluence-fetch
description: Use when the user provides a Confluence Cloud page URL or asks an agentic tool to fetch Confluence page context with confluence-fetch. Typically invoked as `$confluence-fetch {confluence URL}`.
__MANAGED_METADATA__
---

# Confluence Fetch

Use `confluence-fetch` to fetch Confluence Cloud page context from a URL. The default output is Markdown on stdout. JSON is available when structured fields are needed.

## Core Rule

When the user invokes `$confluence-fetch {confluence URL}`, treat the text after the skill name as the Confluence URL to fetch.

Prefer the published CLI:

```text
uvx confluence-fetch "<confluence URL>"
```

The explicit command form is also valid:

```text
uvx confluence-fetch fetch "<confluence URL>"
```

## Setup

The common setup path is:

```text
CONFLUENCE_TOKEN=<api token>
uvx confluence-fetch config set-email "you@example.com"
```

Tokens come from environment variables only. Never store token values in config or in generated files. The config file stores token environment variable names and optional Confluence account email values.

## Fetching

Fetch Markdown:

```text
uvx confluence-fetch "<confluence URL>"
```

Fetch JSON with structured data and Markdown fields:

```text
uvx confluence-fetch fetch --format json "<confluence URL>"
```

Include comments only when the user asks for discussion context:

```text
uvx confluence-fetch fetch --comments "<confluence URL>"
```

Download image assets only when the user asks for local images:

```text
uvx confluence-fetch fetch --download-images --assets-dir ./confluence-assets "<confluence URL>"
```

Write payload output to a file:

```text
uvx confluence-fetch fetch -o page.md "<confluence URL>"
```

## Auth And Config

Token env resolution order:

1. `--token-env`
2. matching domain override from config
3. `[defaults].token_env_var`
4. built-in `CONFLUENCE_TOKEN`

Useful config commands:

```text
uvx confluence-fetch config show
uvx confluence-fetch config set-default-token-env CONFLUENCE_TOKEN
uvx confluence-fetch config set-domain-token-env tenant.atlassian.net TENANT_CONFLUENCE_TOKEN
uvx confluence-fetch config remove-domain tenant.atlassian.net
```

## Output Handling

Stdout is payload only: Markdown by default, JSON with `--format json`. Stderr is for diagnostics, progress, and errors. Parse JSON output before summarizing it, and summarize relevant fields instead of dumping large raw payloads unless the user asks.

Bare page IDs are not supported. Always pass the Confluence URL.
"""


def render_skill(version: str) -> str:
    """Render the sole skill template with the exact CLI version and its digest."""
    metadata = (
        f"metadata:\n  managed-by: {MANAGED_BY}\n"
        f"  managed-version: {json.dumps(version)}\n"
        '  managed-content-sha256: ""'
    )
    text = _SKILL_TEMPLATE.replace("__MANAGED_METADATA__", metadata)
    parsed = parse_metadata(text)
    start, end = parsed.hash_span
    return text[:start] + json.dumps(content_digest(text, parsed)) + text[end:]
