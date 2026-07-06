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
uvx confluence-fetch install-skill
uvx confluence-fetch remove-skill
```

By default the skill is written under `~/.agents/skills/confluence-fetch/SKILL.md`. The skill teaches agents to fetch page context with:

```text
uvx confluence-fetch "<confluence URL>"
```

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
