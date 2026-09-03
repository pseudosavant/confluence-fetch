# confluence-fetch

`confluence-fetch` fetches Confluence Cloud pages and turns them into agent-friendly output for CLI tools like Codex CLI and Claude Code.

It is designed for:

- Fetching page context from a Confluence URL
- Returning clean Markdown by default
- Returning structured JSON when needed
- Keeping secrets out of config files

## Why

This tool exists to bring Confluence context into local agent workflows.

The primary use case is:

1. Set a token in an environment variable
2. Set your Confluence account email in config
3. Run `confluence-fetch fetch <confluence-url>`
3. Feed the result into an agent

## Install

Target public install path:

```powershell
uvx confluence-fetch --help
```

Top-level metadata commands:

```powershell
uvx confluence-fetch --about
uvx confluence-fetch --version
```

`--version` prints only the semantic version.

For local development, the repo will also keep a PEP 723 script entry point for `uv run`.

## Quick Start

Set your Confluence token:

```powershell
$env:CONFLUENCE_TOKEN = "<your-token>"
```

Set your Confluence account email:

```powershell
uvx confluence-fetch config set-email "you@example.com"
```

Fetch a page as Markdown:

```powershell
uvx confluence-fetch fetch "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

Fetch the same page as JSON:

```powershell
uvx confluence-fetch fetch --format json "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

Write output to a file:

```powershell
uvx confluence-fetch fetch -o page.md "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

Include comments:

```powershell
uvx confluence-fetch fetch --comments "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

Comment order defaults to best-effort document order. Inline comments with anchor text are rendered top-to-bottom by the first matching occurrence in the page body. Comments whose anchors cannot be matched are rendered at the end in created order.

Use a time-based order when you prefer an unambiguous chronological list:

```powershell
uvx confluence-fetch fetch --comments --comment-order created "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
uvx confluence-fetch fetch --comments --comment-order updated "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

## Config

Optional user config lives at:

```text
~/.confluence-fetch/config.toml
```

The config stores only environment variable names, never secret token values.

Example:

```toml
[defaults]
token_env_var = "CONFLUENCE_TOKEN"
email = "you@example.com"

[domains."sona-systems.atlassian.net"]
token_env_var = "SONA_CONFLUENCE_TOKEN"

[domains."example.atlassian.net"]
token_env_var = "EXAMPLE_CONFLUENCE_TOKEN"
```

Resolution order:

1. `--token-env ENV_VAR`
2. domain-specific config match from the requested Confluence URL
3. `[defaults].token_env_var`
4. built-in default `CONFLUENCE_TOKEN`

Email resolution order:

1. `[defaults].email`
2. `CONFLUENCE_EMAIL`
3. compatibility fallback `confluence_email`

Config commands:

```text
confluence-fetch config show
confluence-fetch config set-default-token-env ENV_VAR
confluence-fetch config set-email EMAIL
confluence-fetch config clear-email
confluence-fetch config set-domain-token-env DOMAIN ENV_VAR
confluence-fetch config remove-domain DOMAIN
```

Example:

```powershell
uvx confluence-fetch config set-domain-token-env sona-systems.atlassian.net SONA_CONFLUENCE_TOKEN
```

`config show` displays the effective token env var names, whether they are set or missing, and the configured default email. It never prints token values.

## Agent Skill

`confluence-fetch` can install a managed `$confluence-fetch` skill for agentic tools:

```powershell
uvx confluence-fetch skill install
uvx confluence-fetch skill status
uvx confluence-fetch skill status --format text
uvx confluence-fetch skill remove
```

By default the skill is written under `~/.agents/skills/confluence-fetch/SKILL.md`. The skill teaches agents to fetch page context with:

```text
uvx confluence-fetch "<confluence URL>"
```

Normally installed CLIs automatically synchronize an already-installed managed skill in this standard location. The running CLI version is the authority. An older pristine skill updates locally on ordinary invocations, including help and version output. Missing and unmanaged skills are left alone. Equal and newer versions are never automatically replaced.

Managed YAML metadata records the CLI version and a SHA-256 content hash. Modified skills and skills with valid versions but missing or invalid hashes are preserved. To replace managed content explicitly:

```text
uvx confluence-fetch skill install --force
```

Installation, even with `--force`, never overwrites unmanaged content or downgrades a newer version. Legacy skills with the old HTML marker migrate once without hash verification. Managed skills with missing or malformed versions receive a fresh replacement. Removal accepts both metadata formats. Removal with `--force` retains its unmanaged-file override. Only `SKILL.md` is managed. Unrelated files remain in place.

All skill commands skip automatic synchronization and return JSON by default. `skill status --format text` reports the path, versions, integrity, and update eligibility in plain text. The existing `install-skill` and `remove-skill` commands remain available as aliases.

Use `--skills-dir PATH` on skill commands for a custom skills root. Custom locations require explicit updates. Repeat that option when using `skill install --force`. Local checkouts, local source installs, and editable builds skip automatic synchronization. Explicit installation still works from development builds, including `uvx --from . confluence-fetch skill install`. Installed wheels remain eligible.

Synchronization does not query package indexes, refresh uv's cache, or update the CLI. Notices go to stderr and never enter JSON stdout. Updates affect future agent skill loading. Instructions already loaded into a running agent session may remain unchanged until the skill is loaded again.

## Output

`confluence-fetch` supports:

- `--format markdown`
- `--format json`
- `--comment-order document`
- `--comment-order created`
- `--comment-order updated`

Markdown is the default.

Diagnostics go to stderr. Payload output goes to stdout unless `--output` is used.

## Development

Implementation target:

- Python `>=3.11`
- installable PyPI package
- PEP 723 wrapper for `uv run`

Run tests and build distributions with:

```text
uv run --extra dev pytest
uv build --no-sources
```

Tests isolate the home directory. To smoke-test a built wheel in a separate environment, run `uv run --extra dev python tests/wheel_smoke.py dist/confluence_fetch-1.1.0-py3-none-any.whl`. The smoke test works offline and uses temporary skill locations. No formatter or linter is configured in this repository.

## Auth

`confluence-fetch` uses Basic auth with a Confluence account email plus API token.

Secrets are not written to config.

### Scoped API Token Permissions

For scoped Confluence API tokens, grant only the scopes needed for the features you use:

| Feature | Required scope |
| --- | --- |
| Fetch page Markdown or JSON | `read:page:confluence` |
| Include comments with `--comments` | `read:comment:confluence` |
| Download image assets with `--download-images` | `read:attachment:confluence` |
| Resolve comment author display names | `read:user:confluence` |

Recommended full token for all current features:

```text
read:page:confluence
read:comment:confluence
read:attachment:confluence
read:user:confluence
```

If `read:user:confluence` is missing, comments still render, but author names fall back to stable account IDs when Confluence does not include display names in the comment payload.

## License

MIT. See `LICENSE`.

## Status

This repo is currently being built around an agent-first v2 spec.
