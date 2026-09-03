# confluence-fetch

`confluence-fetch` turns a Confluence Cloud page URL into clean Markdown or structured JSON for agents, scripts, and local workflows. It can include comments, download page images, and produce payload-only output for reliable automation.

## Prerequisite

`confluence-fetch` is designed to be used with [`uv`](https://docs.astral.sh/uv/getting-started/installation/). Install `uv` before continuing. The documented workflows and managed agent skill use `uvx` to run the tool without requiring a global installation.

You also need a Confluence account email and API token.

## Quick start with an agent

Install the managed agent skill:

```powershell
uvx confluence-fetch skill install
```

Set your Confluence token for the current PowerShell session:

```powershell
$env:CONFLUENCE_TOKEN = "<your-token>"
```

Save your Confluence account email:

```powershell
uvx confluence-fetch config set-email "you@example.com"
```

Then use `$confluence-fetch` in Codex, Claude Code, or another agent harness that supports skills:

> Use $confluence-fetch to fetch this Confluence page with comments and summarize its decisions and action items: `<Confluence URL>`

The skill teaches the agent how to fetch Markdown or JSON, include comments, download images, and handle authentication errors.

## Manage the agent skill

The standard location is `~/.agents/skills/confluence-fetch/SKILL.md`. Normal invocations of an installed CLI, including help and version output, automatically synchronize an already-installed managed skill to the running CLI version. Missing and unmanaged skills are left alone. Skill-management commands skip this automatic check.

Synchronization is local only. It does not query a package index, refresh uv's cache, or update the CLI. The running CLI version is the authority. PEP 440 version comparison prevents downgrades and leaves equal versions unchanged. The skill continues to instruct agents to use `uvx confluence-fetch`.

Each generated `SKILL.md` stores lifecycle data in its YAML `metadata` mapping:

```yaml
metadata:
  managed-by: confluence-fetch
  managed-version: "1.1.0"
  managed-content-sha256: "sha256:<64 lowercase hexadecimal characters>"
```

The version above is illustrative. The generated value exactly matches `uvx confluence-fetch --version`. The SHA-256 hash detects modifications to managed content. It is not a signature or security boundary. No sidecar files are used.

Inspect the path, ownership, versions, integrity, and automatic synchronization eligibility without changing anything:

```powershell
uvx confluence-fetch skill status
uvx confluence-fetch skill status --format text
```

A normal explicit install creates a missing skill or updates a pristine older one. It refuses to overwrite modified or unverifiable managed content. To restore the bundled skill and discard edits to managed content:

```powershell
uvx confluence-fetch skill install --force
```

Install-time `--force` still refuses unmanaged skills and never downgrades a newer version. Removal accepts current and legacy managed skills:

```powershell
uvx confluence-fetch skill remove
```

All three commands accept `--skills-dir PATH`. Custom locations require explicit updates because normal CLI invocations inspect only the standard location. Local source checkouts, direct source installs, and editable builds do not synchronize automatically. Installed wheels remain eligible.

Explicit commands still work during development:

```powershell
uvx --from . confluence-fetch skill install
```

Automatic replacements are atomic and recheck the installed file before replacement. Maintenance failures do not change the primary command's exit status. Notices go to stderr, so payloads on stdout stay valid. Changes affect future skill loading and may require a new agent session.

## What it returns

Markdown is the default output:

```markdown
# 123456789 Example Page

# Page

The converted page content appears here.
```

With `--comments`, the document also contains a `# Discussion` section. JSON output contains structured page, discussion, and asset data together with the rendered Markdown.

An abbreviated JSON result looks like this:

```json
{
  "page": {
    "id": "123456789",
    "title": "Example Page",
    "url": "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page",
    "site": "https://your-domain.atlassian.net"
  },
  "content": {
    "body_markdown": "The converted page content appears here.",
    "document_markdown": "# 123456789 Example Page\n\n# Page\n\nThe converted page content appears here."
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

## Use the CLI directly

After setting your token and email, fetch a page by passing its URL:

```powershell
uvx confluence-fetch "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

The explicit form is also supported:

```powershell
uvx confluence-fetch fetch "https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example+Page"
```

Full page URLs and Confluence `/wiki/x/` short URLs are supported. Bare page IDs are not supported. The requested domain is derived from the URL.

To install the command as a persistent tool instead:

```powershell
uv tool install confluence-fetch
```

The examples below continue to use `uvx confluence-fetch` so they work without a global installation.

## How fetching works

The fetch model has five core rules:

1. Every fetch starts with a full Confluence page URL or a Confluence `/wiki/x/` short URL.
2. The URL determines the Confluence tenant and page. Bare page IDs are rejected.
3. Authentication is resolved from the requested domain, configuration, and environment variables.
4. Confluence page HTML is converted to GitHub-flavored Markdown. Relative page links and image URLs become absolute.
5. The requested payload goes to stdout by default. Progress, diagnostics, and errors go to stderr.

This makes the common case deterministic:

```powershell
uvx confluence-fetch "<Confluence URL>"
```

Add options only when you need JSON, file output, comments, downloaded images, or verbose diagnostics.

## Common fetch tasks

### Return structured JSON

```powershell
uvx confluence-fetch "<Confluence URL>" --format json
```

JSON mode includes structured fields and Markdown fields, including the complete `document_markdown` value.

### Write output to a file

```powershell
uvx confluence-fetch "<Confluence URL>" --output page.md
```

When `--output` is used, the payload is written to the file and stdout stays empty.

### Include comments

```powershell
uvx confluence-fetch "<Confluence URL>" --comments
```

Comments are opt-in. The default `document` order places anchored inline comments according to their first matching location in the page body. Comments without a matching anchor appear afterward in creation order.

Use a time-based order when you want an unambiguous chronological list:

```powershell
uvx confluence-fetch "<Confluence URL>" --comments --comment-order created
uvx confluence-fetch "<Confluence URL>" --comments --comment-order updated
```

Limit or filter the rendered comments:

```powershell
uvx confluence-fetch "<Confluence URL>" --comments --comment-limit 20
uvx confluence-fetch "<Confluence URL>" --comments --comment-kinds inline
```

### Download images

```powershell
uvx confluence-fetch "<Confluence URL>" --download-images --assets-dir ./page-assets
```

Image downloads are best-effort. Failed downloads are reported without failing an otherwise successful page fetch. Markdown image links are rewritten for assets that download successfully.

If `--assets-dir` is omitted, assets are written to `<output-name>.assets` when file output is used. Otherwise they are written to `<page-id>.assets` in the current directory.

## Authentication

`confluence-fetch` uses Basic auth with a Confluence account email and API token. Token values come from environment variables only. They are never written to config.

The token environment variable is selected in this order:

1. `--token-env ENV_VAR`
2. A matching domain override in config
3. `[defaults].token_env_var` in config
4. The built-in `CONFLUENCE_TOKEN` default

The account email is selected in this order:

1. A matching domain email in config
2. `[defaults].email` in config
3. `CONFLUENCE_EMAIL`
4. The compatibility fallback `confluence_email`

### Scoped API token permissions

Grant only the scopes needed for the features you use:

| Feature | Required scope |
| --- | --- |
| Fetch page Markdown or JSON | `read:page:confluence` |
| Include comments with `--comments` | `read:comment:confluence` |
| Download image assets with `--download-images` | `read:attachment:confluence` |
| Resolve comment author display names | `read:user:confluence` |

For all current features, grant:

```text
read:page:confluence
read:comment:confluence
read:attachment:confluence
read:user:confluence
```

If `read:user:confluence` is missing, comments still render. Author names fall back to stable account IDs when Confluence does not return display names.

## Configure multiple Confluence sites

Optional user config lives at `~/.confluence-fetch/config.toml`. It stores email addresses and environment variable names, never token values.

Example:

```toml
[defaults]
token_env_var = "CONFLUENCE_TOKEN"
email = "you@example.com"

[domains."sona-systems.atlassian.net"]
token_env_var = "SONA_CONFLUENCE_TOKEN"
email = "you@sona.example"

[domains."example.atlassian.net"]
token_env_var = "EXAMPLE_CONFLUENCE_TOKEN"
```

Inspect the effective configuration and whether each referenced token variable is set:

```powershell
uvx confluence-fetch config show
```

`config show` never prints token values.

Update configuration with these commands:

```powershell
uvx confluence-fetch config set-default-token-env CONFLUENCE_TOKEN
uvx confluence-fetch config set-email "you@example.com"
uvx confluence-fetch config clear-email
uvx confluence-fetch config set-domain-token-env sona-systems.atlassian.net SONA_CONFLUENCE_TOKEN
uvx confluence-fetch config set-domain-email sona-systems.atlassian.net "you@sona.example"
uvx confluence-fetch config remove-domain-email sona-systems.atlassian.net
uvx confluence-fetch config remove-domain sona-systems.atlassian.net
```

## Automation contract

Payload output goes to stdout by default. Diagnostics, progress, and errors go to stderr. This keeps Markdown and JSON output safe for pipes and automation.

```powershell
uvx confluence-fetch "<Confluence URL>" --format json --no-progress
```

Use `--verbose` for detailed diagnostics on stderr.

Exit codes:

| Code | Meaning |
| ---: | --- |
| `0` | Success |
| `2` | Usage error |
| `10` | Authentication or permission error |
| `20` | Page not found |
| `30` | Rate limited after retries |
| `1` | Other failure |

## Reference

Useful discovery and metadata commands:

```powershell
uvx confluence-fetch --help
uvx confluence-fetch fetch --help
uvx confluence-fetch config --help
uvx confluence-fetch skill --help
uvx confluence-fetch --about
uvx confluence-fetch --version
```

Supported fetch options include:

| Option | Purpose |
| --- | --- |
| `--format markdown|json` | Select the payload format. The default is Markdown. |
| `-o, --output PATH` | Write the payload to a file. |
| `--download-images` | Download image assets and rewrite Markdown links. |
| `--assets-dir PATH` | Select the asset directory. Requires `--download-images`. |
| `--comments` | Include a `# Discussion` section. |
| `--comment-limit N` | Limit root comments per section. The valid range is 1 through 50. |
| `--comment-kinds all|footer|inline` | Select which comment sections to include. |
| `--comment-order created|updated|document` | Select comment ordering. The default is `document`. |
| `--token-env ENV_VAR` | Read the token from the named environment variable. |
| `--verbose` | Write detailed diagnostics to stderr. |
| `--no-progress` | Disable progress output on stderr. |

Agent skill commands return JSON by default. `skill status` also supports text output:

```powershell
uvx confluence-fetch skill status --format text
```

The `install-skill` and `remove-skill` commands remain available as aliases for compatibility.

## Example agent requests

Fetch a page and identify the decisions it records:

> Use $confluence-fetch to fetch `<Confluence URL>`. Summarize the decisions, open questions, and named owners.

Include the discussion when reviewing a proposal:

> Use $confluence-fetch to fetch `<Confluence URL>` with comments. Separate feedback that has been resolved from feedback that still needs action.

Download images when page diagrams matter:

> Use $confluence-fetch to fetch `<Confluence URL>` and download its images. Explain the page using both the written content and the diagrams.

## Development

Install the development environment and run the tests:

```powershell
uv sync --locked --extra dev
uv run pytest
```

Build the distributions:

```powershell
uv build --no-sources
```

The repository also contains a thin PEP 723 wrapper for local execution:

```powershell
uv run confluence_fetch.py --help
```

Tests isolate the home directory. The wheel smoke test uses temporary skill locations and runs without network access.

Project: [github.com/pseudosavant/confluence-fetch](https://github.com/pseudosavant/confluence-fetch)

## License

MIT. See [LICENSE](LICENSE).
