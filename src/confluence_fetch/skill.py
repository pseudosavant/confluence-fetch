from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from confluence_fetch.errors import UsageError


SKILL_NAME = "confluence-fetch"
MANAGED_MARKER = "<!-- managed-by: confluence-fetch -->"


SKILL_MD = f"""---
name: confluence-fetch
description: Use when the user provides a Confluence Cloud page URL or asks an agentic tool to fetch Confluence page context with confluence-fetch. Typically invoked as `$confluence-fetch {{confluence URL}}`.
---

{MANAGED_MARKER}

# Confluence Fetch

Use `confluence-fetch` to fetch Confluence Cloud page context from a URL. The default output is Markdown on stdout; JSON is available when structured fields are needed.

## Core Rule

When the user invokes `$confluence-fetch {{confluence URL}}`, treat the text after the skill name as the Confluence URL to fetch.

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


def default_skills_dir() -> Path:
    return Path.home() / ".agents" / "skills"


def skill_dir(skills_dir: Path | None = None) -> Path:
    return (skills_dir or default_skills_dir()) / SKILL_NAME


def install_skill(skills_dir: Path | None = None) -> dict[str, Any]:
    target = skill_dir(skills_dir)
    target.mkdir(parents=True, exist_ok=True)
    skill_path = target / "SKILL.md"
    previous = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    updated = previous != SKILL_MD
    skill_path.write_text(SKILL_MD, encoding="utf-8")
    return {
        "installed": True,
        "updated": updated,
        "skill": SKILL_NAME,
        "path": str(skill_path),
    }


def remove_skill(skills_dir: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    target = skill_dir(skills_dir)
    skill_path = target / "SKILL.md"
    if not target.exists():
        return {"removed": False, "skill": SKILL_NAME, "path": str(target), "reason": "not_installed"}
    if not skill_path.exists():
        raise UsageError(f"refusing to remove '{target}' because SKILL.md is missing.")
    content = skill_path.read_text(encoding="utf-8")
    if MANAGED_MARKER not in content and not force:
        raise UsageError(
            f"refusing to remove '{target}' because it is not marked as managed by confluence-fetch; "
            "use --force to override."
        )
    shutil.rmtree(target)
    return {"removed": True, "skill": SKILL_NAME, "path": str(target)}
