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
2. Run `confluence-fetch fetch <confluence-url>`
3. Feed the result into an agent

## Install

Target public install path:

```powershell
uvx confluence-fetch --help
```

For local development, the repo will also keep a PEP 723 script entry point for `uv run`.

## Quick Start

Set your Confluence token:

```powershell
$env:CONFLUENCE_TOKEN = "<your-token>"
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

Config commands:

```text
confluence-fetch config show
confluence-fetch config set-default-token-env ENV_VAR
confluence-fetch config set-domain-token-env DOMAIN ENV_VAR
confluence-fetch config remove-domain DOMAIN
```

Example:

```powershell
uvx confluence-fetch config set-domain-token-env sona-systems.atlassian.net SONA_CONFLUENCE_TOKEN
```

`config show` should display effective env var names and whether they are set or missing, but never token values.

## Output

`confluence-fetch` supports:

- `--format markdown`
- `--format json`

Markdown is the default.

Diagnostics go to stderr. Payload output goes to stdout unless `--output` is used.

## Development

Implementation target:

- Python `>=3.11`
- installable PyPI package
- PEP 723 wrapper for `uv run`

## Auth

`confluence-fetch` uses a scoped Confluence Cloud token provided through an environment variable and sent as a Bearer token.

Secrets are not written to config.

## License

MIT. See `LICENSE`.

## Status

This repo is currently being built around an agent-first v2 spec.
