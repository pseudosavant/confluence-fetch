from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from confluence_fetch import __version__
from confluence_fetch.config import (
    clear_default_email,
    default_config_path,
    load_config,
    remove_domain,
    remove_domain_email,
    render_config_show,
    resolve_email,
    resolve_token_env_name,
    set_default_email,
    set_domain_email,
    set_default_token_env_var,
    set_domain_token_env_var,
)
from confluence_fetch.errors import AppError, UsageError
from confluence_fetch.fetcher import emit_result, fetch_document
from confluence_fetch.models import FetchOptions
from confluence_fetch.skill import default_skills_dir, install_skill, remove_skill, skill_status, synchronize_skill
from confluence_fetch.urls import parse_host


PROJECT_URL = "https://github.com/pseudosavant/confluence-fetch"
LICENSE_NAME = "MIT"


def configure_utf8_stdio(*streams: object) -> None:
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, TypeError, ValueError):
            continue


ROOT_DESCRIPTION = """\
confluence-fetch - Fetch Confluence Cloud page context as Markdown or JSON

Happy path:
  1. Set CONFLUENCE_TOKEN in the environment
  2. Set your Confluence email once: confluence-fetch config set-email you@example.com
  3. Fetch a page by passing only the URL:
     confluence-fetch https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example

You usually only need to pass a Confluence URL. When the first argument is a URL,
confluence-fetch automatically treats it as "fetch <url>".
"""

ROOT_EPILOG = f"""\
Usage:
  confluence-fetch <url>
  confluence-fetch fetch <url> [options]
  confluence-fetch config <command>
  confluence-fetch skill install|remove|status
  confluence-fetch install-skill
  confluence-fetch remove-skill

Examples:
  confluence-fetch https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch --help
  confluence-fetch --about
  confluence-fetch fetch --format json https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch fetch --comments https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch config show
  uvx confluence-fetch skill install
  uvx confluence-fetch skill status --format text
  uvx confluence-fetch skill install --force

Commands:
  fetch          Fetch a Confluence page. Usually implicit when you pass a URL directly.
  config         Show or update non-secret config.
  skill          Install, remove, or inspect the managed agent skill.
  install-skill  Install or update the confluence-fetch skill.
  remove-skill   Remove the managed confluence-fetch skill.

Managed skill:
  Normally installed CLIs synchronize an existing managed skill at
  ~/.agents/skills/confluence-fetch/SKILL.md to the running CLI version.
  Older pristine skills update locally. Modified skills are preserved.
  Use uvx confluence-fetch skill install --force for a managed replacement.
  Custom locations need explicit updates. Local source and editable builds skip
  automatic synchronization. Skill commands also skip automatic synchronization.
  This does not update the CLI, query package indexes, or refresh uv caches.
  Changes apply to future skill loading, possibly after a new agent session.

Common fetch options:
  --format markdown|json       Output format. Default: markdown.
  -o, --output PATH            Write the payload to a file instead of stdout.
  --download-images            Download image assets and rewrite Markdown image links.
  --comments                   Include a # Discussion section.
  --comment-limit N            Limit root comments per section. Default: 10, valid range 1..50.
  --comment-kinds all|footer|inline
                               Select footer comments, inline comments, or both. Default: all.
  --comment-order created|updated|document
                               Sort comments by creation time, update time, or best-effort document position. Default: document.
  --token-env ENV_VAR          Read the API token from this environment variable name.

Auth:
  Basic auth only: Confluence account email plus API token.
  Token env resolution: --token-env, domain config override, [defaults].token_env_var, CONFLUENCE_TOKEN
  Email resolution: domain config email, [defaults].email, CONFLUENCE_EMAIL, confluence_email
  Scoped token permissions:
    read:page:confluence        Fetch page content and resolve page URLs.
    read:comment:confluence     Required when using --comments.
    read:attachment:confluence  Required when using --download-images.
    read:user:confluence        Resolve comment author names; otherwise account IDs are used.

Output contract:
  stdout  Payload only (Markdown by default, JSON with --format json)
  stderr  Diagnostics, progress, and errors

Accepted URL forms:
  Full Confluence page URLs
  Short /wiki/x/ URLs

Local and package entrypoints:
  uvx confluence-fetch --help
  uv run confluence_fetch.py --help

Exit codes:
  0 success
  2 usage
  10 auth
  20 not found
  30 rate limited
  1 other failure

Project:
  {PROJECT_URL}
License:
  {LICENSE_NAME}
"""

ABOUT_TEXT = f"""confluence-fetch {__version__}

Agent-first CLI for fetching Confluence Cloud page context as Markdown or JSON.

Project: {PROJECT_URL}
License: {LICENSE_NAME}
"""

FETCH_DESCRIPTION = """\
Fetch a Confluence page by URL.

Happy path:
  confluence-fetch <url>

Explicit form:
  confluence-fetch fetch <url>

Most runs should only need the URL. Add flags only when you need a non-default
format, file output, image downloads, comments, or verbose diagnostics.
"""

FETCH_EPILOG = """\
Examples:
  confluence-fetch https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch fetch --format json https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch fetch -o page.md https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch fetch --comments https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch fetch --comments --comment-order created https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example
  confluence-fetch fetch --download-images --assets-dir assets https://your-domain.atlassian.net/wiki/spaces/ENG/pages/123456789/Example

Required setup:
  Set a token env var, usually CONFLUENCE_TOKEN
  Set your email once: confluence-fetch config set-email you@example.com

Scoped token permissions:
  read:page:confluence        Fetch page content and resolve page URLs.
  read:comment:confluence     Required when using --comments.
  read:attachment:confluence  Required when using --download-images.
  read:user:confluence        Resolve comment author names; otherwise account IDs are used.

Notes:
  Default output format is Markdown
  JSON output includes structured fields plus Markdown fields
  Comments are opt-in with --comments
  Default comment order is document: matched inline comment anchors are rendered top-to-bottom; unmatched comments come last by creation time
  Bare page IDs are not supported; pass a Confluence URL
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="confluence-fetch",
        description=ROOT_DESCRIPTION,
        epilog=ROOT_EPILOG,
        usage="confluence-fetch <url> | confluence-fetch fetch <url> [options] | confluence-fetch config <command>",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
    )
    parser.add_argument("--about", action="store_true", help="show project and license information and exit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch a Confluence page and emit Markdown or JSON.",
        usage="confluence-fetch <url> | confluence-fetch fetch <url> [options]",
        formatter_class=argparse.RawTextHelpFormatter,
        description=FETCH_DESCRIPTION,
        epilog=FETCH_EPILOG,
    )
    fetch_parser.add_argument("url", help="Confluence page URL. Full page URLs and short /wiki/x/ URLs are supported.")
    fetch_parser.add_argument("--token-env", help="Read the API token from this environment variable name.")
    fetch_parser.add_argument("-o", "--output", type=Path, help="Write the payload to a file instead of stdout.")
    fetch_parser.add_argument(
        "--format",
        dest="format_name",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. Default: markdown.",
    )
    fetch_parser.add_argument(
        "--download-images",
        action="store_true",
        help="Download image assets and rewrite Markdown image links to local files.",
    )
    fetch_parser.add_argument(
        "--assets-dir",
        type=Path,
        help="Directory for downloaded assets. Requires --download-images.",
    )
    fetch_parser.add_argument("--comments", action="store_true", help="Include a # Discussion section.")
    fetch_parser.add_argument(
        "--comment-limit",
        type=int,
        default=10,
        help="Limit root comments per section. Valid range: 1..50. Default: 10.",
    )
    fetch_parser.add_argument(
        "--comment-kinds",
        choices=("all", "footer", "inline"),
        default="all",
        help="Which comment sections to include when --comments is enabled. Default: all.",
    )
    fetch_parser.add_argument(
        "--comment-order",
        choices=("created", "updated", "document"),
        default="document",
        help="Sort comments by creation time, update time, or best-effort document position. Default: document.",
    )
    fetch_parser.add_argument("--verbose", action="store_true", help="Write detailed diagnostics to stderr.")
    fetch_parser.add_argument("--no-progress", action="store_true", help="Disable progress output on stderr.")

    config_parser = subparsers.add_parser(
        "config",
        help="Show or update non-secret config.",
        formatter_class=argparse.RawTextHelpFormatter,
        description=(
            "Show or update config at ~/.confluence-fetch/config.toml.\n"
            "Config stores env var names and email values, never token values."
        ),
        epilog=(
            "Examples:\n"
            "  confluence-fetch config show\n"
            "  confluence-fetch config set-email you@example.com\n"
            "  confluence-fetch config set-default-token-env CONFLUENCE_TOKEN\n"
            "  confluence-fetch config set-domain-token-env sona-systems.atlassian.net SONA_CONFLUENCE_TOKEN"
        ),
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show", help="Show effective config and env var presence.")

    set_default_parser = config_subparsers.add_parser(
        "set-default-token-env",
        help="Set the default token env var name.",
    )
    set_default_parser.add_argument("env_var")

    set_email_parser = config_subparsers.add_parser(
        "set-email",
        help="Set the default Confluence account email for Basic auth.",
    )
    set_email_parser.add_argument("email")

    config_subparsers.add_parser(
        "clear-email",
        help="Remove the default Confluence account email from config.",
    )

    set_domain_parser = config_subparsers.add_parser(
        "set-domain-token-env",
        help="Set a domain-specific token env var override.",
    )
    set_domain_parser.add_argument("domain")
    set_domain_parser.add_argument("env_var")

    set_domain_email_parser = config_subparsers.add_parser(
        "set-domain-email",
        help="Set a domain-specific Confluence account email for Basic auth.",
    )
    set_domain_email_parser.add_argument("domain")
    set_domain_email_parser.add_argument("email")

    remove_domain_email_parser = config_subparsers.add_parser(
        "remove-domain-email",
        help="Remove a domain-specific email override.",
    )
    remove_domain_email_parser.add_argument("domain")

    remove_domain_parser = config_subparsers.add_parser(
        "remove-domain",
        help="Remove a domain-specific override.",
    )
    remove_domain_parser.add_argument("domain")

    skill_parser = subparsers.add_parser(
        "skill",
        help="Install, remove, or inspect the managed agent skill.",
        description="Manage the confluence-fetch skill. These commands skip automatic synchronization.",
    )
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)
    descriptions = {
        "install": "Install a missing skill or update a pristine older managed skill. Never overwrite unmanaged content.",
        "remove": "Remove SKILL.md and its directory if empty. Preserve unrelated files.",
        "status": "Inspect skill version, integrity, and automatic synchronization eligibility without writing files.",
    }
    for command, description in descriptions.items():
        parsers = [skill_subparsers.add_parser(command, help=description, description=description)]
        if command in {"install", "remove"}:
            alias = subparsers.add_parser(f"{command}-skill", help=f"Alias for skill {command}.", description=description)
            alias.set_defaults(skill_command=command)
            parsers.append(alias)
        for command_parser in parsers:
            command_parser.add_argument(
                "--skills-dir", type=Path,
                help="Skills root directory. Default: ~/.agents/skills. Custom locations require explicit updates.",
            )
            if command == "install":
                command_parser.add_argument(
                    "--force", action="store_true",
                    help="Replace altered or unverifiable managed content. Never overwrite unmanaged or newer skills.",
                )
            elif command == "remove":
                command_parser.add_argument("--force", action="store_true", help="Remove even if the skill is not managed.")
            else:
                command_parser.add_argument(
                    "--format", dest="format_name", choices=("json", "text"), default="json",
                    help="Output format. Default: json, matching other skill commands.",
                )
    return parser


def normalize_argv(argv: Sequence[str]) -> list[str]:
    args = list(argv)
    if not args:
        return args
    first = args[0]
    if first in {"fetch", "config", "skill", "install-skill", "remove-skill"}:
        return args
    if first.startswith("-"):
        return args
    if first.startswith(("http://", "https://")):
        return ["fetch", *args]
    return args


def validate_fetch_args(args: argparse.Namespace) -> None:
    if args.assets_dir and not args.download_images:
        raise UsageError("--assets-dir requires --download-images.")
    if (args.comment_limit != 10 or args.comment_kinds != "all" or args.comment_order != "document") and not args.comments:
        raise UsageError("--comment-limit, --comment-kinds, and --comment-order require --comments.")
    if not 1 <= args.comment_limit <= 50:
        raise UsageError("--comment-limit must be in the range 1..50.")


def run_fetch(args: argparse.Namespace, *, stdout: object, stderr: object, env: dict[str, str], home: Path | None) -> int:
    validate_fetch_args(args)
    host = parse_host(args.url)
    config_path = default_config_path(home)
    config = load_config(config_path)
    token_env_name = resolve_token_env_name(host, config, args.token_env)
    token = env.get(token_env_name, "")
    if not token:
        raise UsageError(
            f"Token env var {token_env_name!r} is missing or empty. "
            "Set it in the environment or choose a different env var with --token-env."
        )
    auth_email = resolve_email(host, config, env=env)
    if not auth_email:
        raise UsageError(
            "Confluence account email is required for Basic auth. "
            "Set it with `confluence-fetch config set-email <email>`, "
            "`confluence-fetch config set-domain-email <domain> <email>`, or use CONFLUENCE_EMAIL."
        )

    options = FetchOptions(
        token_env_name=token_env_name,
        auth_email=auth_email,
        format_name=args.format_name,
        output_path=args.output,
        download_images=args.download_images,
        assets_dir=args.assets_dir,
        comments=args.comments,
        comment_limit=args.comment_limit,
        comment_kinds=args.comment_kinds,
        comment_order=args.comment_order,
        verbose=args.verbose,
        no_progress=args.no_progress,
    )
    result = fetch_document(args.url, options, token=token, stdout=stdout, stderr=stderr)
    emit_result(result, options, stdout)
    return 0


def run_config(args: argparse.Namespace, *, stdout: object, stderr: object, env: dict[str, str], home: Path | None) -> int:
    config_path = default_config_path(home)
    if args.config_command == "show":
        config = load_config(config_path)
        stdout.write(render_config_show(config_path, config, env=env))
        return 0
    if args.config_command == "set-default-token-env":
        set_default_token_env_var(args.env_var, path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    if args.config_command == "set-email":
        set_default_email(args.email, path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    if args.config_command == "clear-email":
        clear_default_email(path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    if args.config_command == "set-domain-token-env":
        set_domain_token_env_var(args.domain, args.env_var, path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    if args.config_command == "set-domain-email":
        set_domain_email(args.domain, args.email, path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    if args.config_command == "remove-domain-email":
        remove_domain_email(args.domain, path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    if args.config_command == "remove-domain":
        remove_domain(args.domain, path=config_path)
        stderr.write(f"Updated {config_path}\n")
        return 0
    raise UsageError("Unknown config command.")


def write_json_payload(payload: object, stdout: object) -> None:
    stdout.write(json.dumps(payload, indent=2))
    stdout.write("\n")


def run_skill(args: argparse.Namespace, *, stdout: object, home: Path | None) -> int:
    selected = args.skills_dir if args.skills_dir is not None else default_skills_dir(home)
    try:
        if args.skill_command == "install":
            payload = install_skill(selected, force=args.force)
        elif args.skill_command == "remove":
            payload = remove_skill(selected, force=args.force)
        else:
            payload = skill_status(args.skills_dir, home=home)
    except (OSError, UnicodeError) as exc:
        raise AppError(f"Unable to {args.skill_command} skill: {exc}") from exc
    if getattr(args, "format_name", "json") == "text":
        for key, value in payload.items():
            display = "not applicable" if value is None else str(value).lower() if isinstance(value, bool) else value
            stdout.write(f"{key.replace('_', ' ').capitalize()}: {display}\n")
    else:
        write_json_payload(payload, stdout)
    return 0


def is_skill_command(argv: Sequence[str]) -> bool:
    # The only root options take no values. Stop at the first positional token
    # so a fetch URL or an option value cannot masquerade as a skill command.
    first = next((arg for arg in argv if not arg.startswith("-")), None)
    return first in {"skill", "install-skill", "remove-skill"}


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: object | None = None,
    stderr: object | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> int:
    active_stdout = stdout if stdout is not None else sys.stdout
    active_stderr = stderr if stderr is not None else sys.stderr
    if stdout is None:
        configure_utf8_stdio(active_stdout)
    if stderr is None:
        configure_utf8_stdio(active_stderr)
    active_env = env if env is not None else dict(os.environ)
    parser = build_parser()

    try:
        parsed_argv = normalize_argv(list(argv) if argv is not None else sys.argv[1:])
        if not is_skill_command(parsed_argv):
            synchronize_skill(stderr=active_stderr, home=home)
        if not parsed_argv or parsed_argv in (["--help"], ["-h"]):
            parser.print_help(file=active_stdout)
            return 0
        if parsed_argv == ["--about"]:
            active_stdout.write(ABOUT_TEXT)
            return 0
        if parsed_argv in (["--version"], ["-v"]):
            active_stdout.write(f"{__version__}\n")
            return 0
        args = parser.parse_args(parsed_argv)
        if args.command == "fetch":
            return run_fetch(args, stdout=active_stdout, stderr=active_stderr, env=active_env, home=home)
        if args.command == "config":
            return run_config(args, stdout=active_stdout, stderr=active_stderr, env=active_env, home=home)
        if args.command in {"skill", "install-skill", "remove-skill"}:
            return run_skill(args, stdout=active_stdout, home=home)
        raise UsageError("A command is required.")
    except AppError as exc:
        active_stderr.write(f"Error: {exc}\n")
        return exc.exit_code
