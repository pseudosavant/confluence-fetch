# Spec Draft: `confluence-fetch` v2

## Purpose

Build a new version of `confluence-fetch` that fetches Confluence Cloud page content and emits LLM-friendly Markdown, while also being publishable as an installable Python CLI so the preferred invocation is:

```powershell
uvx confluence-fetch --help
```

The rebuilt tool must also retain a PEP 723 script entry point so local execution with `uv run` remains first-class during development.

License:

- MIT

Primary audience:

- Agentic coding tools such as Codex CLI and Claude Code

Secondary audience:

- Humans invoking the tool directly

## Review-Derived Constraints

This draft is based on the current `confluence_cli.py` implementation in this repo.

Key findings that should shape v2:

- The current positional page URL is only used to extract the page ID; the actual API base URL is resolved independently from environment/defaults. In v2, a full page URL must also establish the target tenant unless an explicit CLI option overrides it.
- The current `--include-images` flag silently changes output-path behavior and forces output into a generated folder. In v2, asset download location must be explicit.
- The current `--comments N` flag is ambiguous because it sounds like a mode toggle but actually means a numeric root-comment limit. In v2, inclusion and limit should be separate arguments.
- The current `--get-cloudid` helper behaves more like a separate command than a fetch option. In v2, it should be a subcommand.
- The current script is a single-file PEP 723 script, which is convenient for `uv run` but not sufficient by itself for `uvx confluence-fetch`. V2 must be an installable package with a console entry point.

## Agent-First Design Principles

Because the main caller is an LLM-driven CLI agent, v2 should optimize for explicitness over terseness.

Required design principles:

- Stdout is reserved for requested payloads only
- Diagnostics, progress, and errors go to stderr only
- Argument names must be unambiguous and not overload boolean-vs-numeric meanings
- Resolution rules must be deterministic and documented in `--help`
- Ambient environment should be optional, not magical; explicit CLI arguments win
- Missing tenant/auth context should fail fast with a corrective message instead of silently guessing a placeholder site
- Help text should be concise but information-dense, with exact precedence rules and copy-pasteable examples for agents
- Exit codes and output contracts must remain stable across patch releases

## Scope

V2 should preserve these useful behaviors from v1:

- Accept a Confluence page target as a full URL or Confluence short URL.
- Fetch rendered page content from Confluence Cloud APIs.
- Convert the HTML body to GitHub-flavored Markdown suitable for LLM ingestion.
- Optionally append a discussion section with footer and inline comments.
- Optionally download page images/attachments and rewrite Markdown image links to local files.
- Support retry/backoff for rate limits and transient failures.
- Return stable non-zero exit codes for automation.

## Recommended CLI

Recommended public shape:

```text
confluence-fetch fetch URL [options]
confluence-fetch config show
confluence-fetch config set-default-token-env ENV_VAR
confluence-fetch config set-domain-token-env DOMAIN ENV_VAR
confluence-fetch config remove-domain DOMAIN
confluence-fetch skill install
confluence-fetch skill status [--format json|text]
confluence-fetch skill remove
confluence-fetch install-skill
confluence-fetch remove-skill
```

Compatibility requirement:

- None. V2 should optimize for agent clarity, not for the legacy flat flag interface.

### `fetch`

`URL` accepts:

- A full page URL like `https://tenant.atlassian.net/wiki/spaces/ENG/pages/123456789/Page`
- A short Confluence URL like `https://tenant.atlassian.net/wiki/x/EQBfsg`

Recommended options:

- `--token-env ENV_VAR`
  Explicit environment variable name to read the API token from
- `-o, --output PATH`
  Write Markdown to file; stdout remains the default when this is omitted
- `--format markdown|json`
  Output format for stdout or `--output`; default `markdown`
- `--download-images`
  Download image assets and localize image links
- `--assets-dir PATH`
  Explicit output directory for downloaded assets; if omitted and `--download-images` is set, default to a deterministic sibling directory
- `--comments`
  Append a `# Discussion` section
- `--comment-limit N`
  Limit root comments per rendered section; default `10`, valid range `1..50`
- `--comment-kinds all|footer|inline`
  Default `all`
- `--comment-order created|updated|document`
  Sort comments by creation time, update time, or best-effort document position; default `document`
- `--verbose`
  Log diagnostics to stderr
- `--no-progress`
  Disable spinner/progress output on stderr

Behavior:

- A URL is required; bare page IDs are not supported
- The requested Confluence domain is derived from the URL and used for config lookup and token resolution

### `config`

Recommended commands:

- `confluence-fetch config show`
- `confluence-fetch config set-default-token-env ENV_VAR`
- `confluence-fetch config set-email EMAIL`
- `confluence-fetch config clear-email`
- `confluence-fetch config set-domain-token-env DOMAIN ENV_VAR`
- `confluence-fetch config remove-domain DOMAIN`

Behavior requirements:

- Auto-load `~/.confluence-fetch/config.toml` on every run
- Create the config file on `config set-*` if it does not exist
- Preserve unrelated existing config where practical when updating values
- `config show` must display the effective config clearly
- `config show` should display env var names plus whether each resolved env var is currently set or missing, but must never print token values
- `config show` should display the configured default email if present
- Config stores only non-secret defaults and env var names, never token values

### Top-Level Metadata

Recommended commands:

- `confluence-fetch --about`
- `confluence-fetch --version`

Behavior requirements:

- `--about` prints the command name, package version, one-sentence summary, project URL, and license.
- `--version` prints only the semantic version.
- Running `confluence-fetch` with no arguments prints the top-level help and returns success.
- Top-level help should include the project URL and license after the command/help content.

### Agent Skill

Commands:

- `uvx confluence-fetch skill install [--force] [--skills-dir PATH]`
- `uvx confluence-fetch skill status [--format json|text] [--skills-dir PATH]`
- `uvx confluence-fetch skill remove [--force] [--skills-dir PATH]`

The existing `install-skill` and `remove-skill` forms remain aliases. Skill commands return JSON on stdout by default. Status also supports plain text. Diagnostics go to stderr. All skill commands skip automatic synchronization.

The standard path is `~/.agents/skills/confluence-fetch/SKILL.md`. The sole canonical skill template retains the name, description, instructions, and `uvx confluence-fetch` examples. `$confluence-fetch {confluence URL}` means to fetch that URL. Files use UTF-8 without a BOM, LF line endings, and a trailing newline.

Lifecycle fields live under the YAML `metadata` mapping:

```yaml
metadata:
  managed-by: confluence-fetch
  managed-version: "1.1.0"
  managed-content-sha256: "sha256:<64 lowercase hexadecimal characters>"
```

`managed-version` is a quoted string that exactly matches the CLI's runtime `confluence_fetch.__version__`. There is no top-level version or sidecar file. Unrelated supported metadata in the canonical template is retained. The old `<!-- managed-by: confluence-fetch -->` marker remains a legacy indicator. A conflicting `metadata.managed-by` always makes the file unmanaged. Newly generated skills use front matter only.

The SHA-256 hash covers the entire file with only the hash scalar replaced by `""`. Normalize CRLF and CR to LF, encode as UTF-8, then hash. Verification uses the installed file's own stored hash. Parse YAML to locate the field without reserializing it. The hash detects modifications. It is not a signature or security boundary.

Ordinary invocations, including fetching, config inspection, help, no-argument help, version, and about output, perform best-effort local synchronization. Only an existing managed skill at the standard path is considered. Compare versions with PEP 440 semantics:

| Installed state | Automatic action |
| --- | --- |
| Absent or unmanaged | Leave unchanged |
| Legacy marker without a version | Migrate from version 0 without hash verification |
| Managed version missing or malformed | Replace with the canonical skill before considering integrity |
| Valid version equal to or newer than the CLI | Leave unchanged |
| Older version with matching normalized hash | Replace with the canonical skill |
| Older version with missing, malformed, or mismatched hash | Preserve and recommend `uvx confluence-fetch skill install --force` |

An invalid running CLI version skips automatic synchronization. Local checkouts, direct local source installations, and editable installations also skip it. Use installed-distribution metadata and PEP 610 provenance. Local source directories and archives are excluded. Installed wheels, including direct wheel installations, remain eligible when the runtime package matches the distribution. Unknown provenance is conservatively excluded. Do not infer launcher behavior or uvx usage.

An explicit install creates a missing skill, updates an older pristine managed skill, and leaves a current pristine skill unchanged. A valid managed version with missing, malformed, or mismatched integrity requires `--force`. Installation with `--force` can replace altered managed content. It cannot overwrite unmanaged content or downgrade a newer version. Missing or malformed managed versions use the same recovery rule as automatic synchronization. Explicit commands work in development builds and custom locations. Automatic invocations never rediscover custom paths. Repeat `--skills-dir PATH` for custom updates.

Status is read-only. It exposes the selected path, standard or custom location, installed and managed flags, CLI and installed versions, version relation, integrity, recovery state, automatic eligibility, development exclusion reason, and force recommendation where applicable.

Replacement writes a complete temporary file in the target directory, flushes and closes it, rechecks the installed bytes, then uses atomic `os.replace`. If the observed file changes, abandon the replacement. Clean up temporary files on failure. Do not wait for locks. Automatic failures never affect the primary exit code. Successful updates produce one stderr notice with old version, new version, and path. Older altered files produce one stderr notice with the force command. Other ordinary no-op states are quiet.

Removal recognizes front matter and legacy management. It refuses unmanaged content unless `--force` is provided. Only `SKILL.md` is removed, followed by the skill directory if empty. Preserve unrelated files and reject unexpected or linked skill paths. Installation refuses a nonempty directory without `SKILL.md`.

Synchronization does not query package indexes, refresh uv's cache, or update the CLI. The running CLI supplies the skill. Updates affect future skill loading and may require a new agent session to replace instructions already loaded by an agent.

## Resolution Rules

### Tenant resolution

V2 must not use a placeholder tenant default for normal fetches.

Resolution order:

1. `fetch` requires a URL input.
2. Derive the tenant host from the requested Confluence URL.
3. Resolve the cloud ID internally when needed.

If a site root is known, the tool should resolve the cloud ID automatically when needed and construct the Atlassian API gateway base internally. That internal API base should not be a required user-facing concept.

Agent-first quick-start target:

- If the caller provides a full Confluence page URL plus `CONFLUENCE_TOKEN` and configures a default email, that should be enough for a successful fetch in the common case
- Cloud ID lookup should remain an internal implementation detail unless a later troubleshooting need justifies a public command

## Local Config

Use a single user config file at:

```text
~/.confluence-fetch/config.toml
```

The config file should support:

- A global default token env var name for the common single-instance case
- Optional domain-specific overrides that map a requested Confluence domain to the token env var name that should be used for that domain

Recommended shape:

```toml
[defaults]
token_env_var = "CONFLUENCE_TOKEN"
email = "you@example.com"

[domains."sona-systems.atlassian.net"]
token_env_var = "SONA_CONFLUENCE_TOKEN"

[domains."client-a.atlassian.net"]
token_env_var = "CLIENT_A_CONFLUENCE_TOKEN"
```

Rationale:

- Most users only need one token, so `CONFLUENCE_TOKEN` plus a full page URL should work with zero config
- Multi-instance users can supply a URL and let the tool infer the correct token env from the URL host
- The config contains no secrets, only pointers to environment variables

### Token resolution

Recommended precedence:

1. If `--token-env` is provided, read the token from that env var
2. Else derive the requested Confluence host from the URL and check `domains."<host>".token_env_var` in `~/.confluence-fetch/config.toml`
3. Else if `[defaults].token_env_var` is configured, use that env var
4. Else fall back to the built-in default env var name `CONFLUENCE_TOKEN`
5. Then read the actual token value from the resolved environment variable name
6. If the env var value is missing or empty, fail with a clear usage/auth error

Email precedence:

1. If `[defaults].email` is configured, use that email
2. Else use `CONFLUENCE_EMAIL` if present
3. Else use compatibility fallback `confluence_email` if present
4. Else fail with a clear usage/auth error

### Important limitation

A domain-to-token mapping assumes one preferred token per tenant host.

That is the right default for the primary use case, but v2 should still support `--token-env` as an explicit override when:

- the same Confluence host needs multiple identities
- an automation flow wants to force a specific credential
- a user wants to bypass config inference temporarily

### Authentication

Canonical environment variable names should be uppercase:

- `CONFLUENCE_TOKEN`
- `CONFLUENCE_EMAIL`

Compatibility recommendation:

- None required for v2 unless you decide to retain `CONFLUENCE_TOKEN` as a temporary alias.

Recommended auth mode:

- Required: Atlassian API token in `CONFLUENCE_TOKEN`
- Required: Confluence account email from config or `CONFLUENCE_EMAIL`
- Send requests using Basic auth with `email:token` to Atlassian's gateway endpoints

Recommended UX:

- Do not expose raw API base URLs as part of the normal public setup
- Do not implement OAuth token flows in v2 unless a later documented need emerges
- Fail clearly if the resolved env var name is set in config/flags but the actual environment variable is missing or empty
- Do not add a command that attempts to persistently set shell environment variables across platforms
- If auth persistence is ever added later, use a secure credential store rather than plain-text config

## Output Contract

Markdown output should preserve the current high-value behavior:

- Top-level title line:

```md
# {pageId} {title}
```

- Page section:

```md
# Page
{body_markdown}
```

- Optional discussion section:

```md
# Discussion
{discussion_markdown}
```

Additional output rules:

- File output uses UTF-8 with LF newlines
- Stdout/stderr use the process stream encoding
- Trailing whitespace is trimmed outside fenced code blocks
- Blank lines are collapsed to at most two outside fenced code blocks
- Relative image URLs and relative page links should be normalized to absolute URLs before Markdown emission
- The default success payload for `fetch` is Markdown on stdout
- If `--output` is used, stdout should stay empty unless a future explicit `--print-path` mode is added

## JSON Contract

When `--format json` is requested, emit a single JSON document on stdout or to the output file.

Recommended top-level shape:

```json
{
  "page": {
    "id": "123456789",
    "title": "Example",
    "url": "https://tenant.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
    "site": "https://tenant.atlassian.net"
  },
  "content": {
    "body_markdown": "...",
    "document_markdown": "# 123456789 Example\n\n# Page\n..."
  },
  "discussion": {
    "included": false,
    "markdown": null,
    "footer_comments": [],
    "inline_comments": []
  },
  "assets": {
    "downloaded": false,
    "directory": null,
    "files": []
  }
}
```

Requirements:

- JSON mode should include both structured fields and Markdown fields where useful
- JSON mode should include `document_markdown`
- JSON mode should include comment structures plus Markdown snippets for rendered comment bodies
- JSON mode should include asset metadata when `--download-images` is used
- JSON mode should be stable and machine-oriented
- Diagnostics must still go to stderr, never mixed into stdout JSON

## Help Contract

`--help` should be written for agents, not marketing copy.

It must include:

- One-sentence summary of what the command returns on stdout
- Exact accepted URL forms
- Argument precedence for tenant resolution
- Canonical environment variables and config keys
- Exact meaning of `--comments`, `--comment-limit`, `--format`, and `--download-images`
- Statement that diagnostics go to stderr and payload goes to stdout
- Exit codes
- At least one example for URL input, file output, and config commands
- A short note about the installable package vs local `uv run` script entry point
- A shortest-path setup example that uses `CONFLUENCE_TOKEN`, `config set-email`, and a full page URL
- Project URL and MIT license in the top-level no-argument help footer

## Comments

Preserve the current separation between footer and inline comments.

Recommended rendering rules:

- Render oldest to newest within the selected window
- If more than `--comment-limit N` root comments exist in a section, keep the most recent `N` roots and render that retained window oldest to newest
- Include inline comment selection context using `On:`
- Resolve author display names when permitted; otherwise fall back to account IDs or stable labels
- Default comment rendering order is `document`: sort inline comments by the first matching occurrence of their anchor text in the rendered page body
- If an inline comment anchor has multiple matches in `document` order, use the first occurrence
- If an inline comment anchor cannot be matched in `document` order, render it after matched comments in created order
- `created` and `updated` comment orders should be available for users who prefer time-based ordering without document-position ambiguity

## Images and Attachments

V2 should make asset behavior explicit:

- `--download-images` must not silently reinterpret a user-supplied output path
- If image download is requested, the asset directory must be predictable and documented
- Download failures for individual images should be logged and should not fail the whole run
- Best-effort image behavior should be the same in both Markdown and JSON mode

## Exit Codes

Carry forward the current exit-code contract unless there is a strong reason to change it:

- `0` success
- `2` usage error
- `10` auth/permission
- `20` not found
- `30` rate limited after retries
- `1` other failure

## Packaging and Publishing

V2 must be both:

- An installable Python package
- A repo-local PEP 723 script entry point for `uv run`

### Packaging requirements

- Target Python `>=3.11`
- Add `pyproject.toml`
- Use a standard build backend
- Expose a console script entry point named `confluence-fetch`
- Move implementation into a package module, for example under `src/confluence_fetch/`
- Keep a thin `confluence_fetch.py` script with PEP 723 metadata that imports and calls the packaged `main()`

### Publishing requirements

- Build with `uv build --no-sources`
- Publish with `uv publish`
- Prefer Trusted Publishing if this will be released from CI
- Include an MIT `LICENSE` file in the repo and published package metadata

Important naming constraint:

- If the desired user command is exactly `uvx confluence-fetch`, the published package name on the configured package index likely also needs to be `confluence-fetch`
- If `confluence-fetch` is unavailable, choose a new public name and use it consistently for both the distribution name and console command so the invocation stays simple, for example `uvx <new-name>`
- If that package name is unavailable, the fallback is a different distribution name plus:

```powershell
uvx --from <distribution-name> confluence-fetch --help
```

## Testing Requirements

V2 needs broader test coverage than v1 currently has.

Add tests for:

- CLI parsing and mutual-exclusion behavior
- URL-derived tenant resolution
- Environment variable precedence
- Config auto-load behavior
- `config show` output
- `config set-*` and `config remove-domain` file-update behavior
- Domain-to-token-env lookup behavior
- stdout vs stderr contract
- Output-path and asset-directory semantics
- Comment-limit behavior
- Relative URL normalization
- Package console entry point smoke test
- PEP 723 script smoke test

## Status

The product decisions needed for an implementation handoff are now resolved:

- public name: `confluence-fetch`
- Python baseline: `>=3.11`
- built-in auth env var: `CONFLUENCE_TOKEN`
- `fetch` requires a URL
- JSON mode includes both structured data and Markdown fields
- config updates do not need round-trip formatting preservation
- image download is best-effort
- license: MIT
