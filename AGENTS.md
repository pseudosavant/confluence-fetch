# AGENTS.md

## Purpose

`confluence-fetch` is an agent-first CLI for fetching Confluence Cloud page context from a URL and emitting machine-friendly Markdown or JSON.

The primary user is an agentic coding tool such as Codex CLI or Claude Code.

## Source Of Truth

- `spec.md` is the behavioral source of truth.
- `README.md` is the public-facing summary.
- If `README.md` and `spec.md` differ, follow `spec.md`.

## Product Rules

- Public package name and command name are `confluence-fetch`.
- `fetch` requires a Confluence URL. Do not support bare page IDs.
- Default output is Markdown.
- `--format json` must remain supported.
- JSON mode should include both structured data and Markdown fields.
- Comments are opt-in.
- Tokens come from environment variables only.
- Never store secrets in config.
- Config lives at `~/.confluence-fetch/config.toml`.
- Config stores env var names, not token values.
- License is MIT.

## CLI Contract

- Stdout is for payload output only.
- Stderr is for diagnostics, progress, and errors.
- Keep argument names explicit and agent-readable.
- CLI flags override config for one-off runs.
- The common setup path should be only:
  set `CONFLUENCE_TOKEN`, then fetch by URL.

## Config Contract

Expected config commands:

- `confluence-fetch config show`
- `confluence-fetch config set-default-token-env ENV_VAR`
- `confluence-fetch config set-domain-token-env DOMAIN ENV_VAR`
- `confluence-fetch config remove-domain DOMAIN`

Expected config shape:

```toml
[defaults]
token_env_var = "CONFLUENCE_TOKEN"

[domains."sona-systems.atlassian.net"]
token_env_var = "SONA_CONFLUENCE_TOKEN"
```

Token env resolution order:

1. `--token-env`
2. matching domain override from config
3. `[defaults].token_env_var`
4. built-in `CONFLUENCE_TOKEN`

`config show` requirements:

- show effective env var names
- show whether each referenced env var is set or missing
- never print token values

## Packaging Rules

- Target Python `>=3.11`.
- Ship as an installable Python package for `uvx confluence-fetch`.
- Also keep a thin PEP 723 wrapper script for local `uv run`.
- Prefer simple direct REST calls over pulling in broad Atlassian wrapper libraries unless there is a clear benefit.

## Implementation Bias

- Favor deterministic behavior over convenience magic.
- Prefer small, explicit modules over one large script.
- Keep Cloud-ID lookup internal unless a real need emerges for a public troubleshooting command.
- Fail clearly when auth config is missing or empty.
- Keep image downloads best-effort in both Markdown and JSON mode.

## Tests

At minimum, cover:

- CLI parsing
- URL-based tenant/domain resolution
- config auto-load and update behavior
- domain-to-token-env lookup
- `config show` behavior
- stdout vs stderr contract
- Markdown and JSON output modes
- comment inclusion behavior
- package entry point and PEP 723 wrapper smoke tests

## Publishing

- Publish to PyPI under `confluence-fetch`.
- Keep the GitHub repo name aligned with the package name.
- Include MIT license metadata and a `LICENSE` file.
