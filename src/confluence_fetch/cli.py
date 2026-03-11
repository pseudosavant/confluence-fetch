from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

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
from confluence_fetch.urls import parse_host


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="confluence-fetch",
        description=(
            "Fetch Confluence Cloud page context and emit Markdown or JSON payloads on stdout. "
            "Diagnostics, progress, and errors are written to stderr."
        ),
        epilog=(
            "Accepted URL forms: full Confluence page URLs and short /wiki/x/ URLs.\n"
            "Token env resolution order: --token-env, domain config override, [defaults].token_env_var, CONFLUENCE_TOKEN.\n"
            "Auth mode: Basic auth only, using a Confluence account email plus API token.\n"
            "Email resolution order: config [defaults].email, CONFLUENCE_EMAIL, confluence_email.\n"
            "Package entry point: uvx confluence-fetch ...\n"
            "Local wrapper: uv run confluence_fetch.py ...\n"
            "Exit codes: 0 success, 2 usage, 10 auth, 20 not found, 30 rate limited, 1 other failure."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch a Confluence page and emit Markdown or JSON.",
        formatter_class=argparse.RawTextHelpFormatter,
        description=(
            "Fetch a Confluence page by URL.\n"
            "Payload output goes to stdout by default; stderr is reserved for diagnostics.\n"
            "Auth uses Basic auth with email plus API token.\n"
            "Shortest path: set CONFLUENCE_TOKEN, set config email, then run confluence-fetch fetch <url>."
        ),
    )
    fetch_parser.add_argument("url", help="Full Confluence page URL or short /wiki/x/ URL.")
    fetch_parser.add_argument("--token-env", help="Environment variable name to read the API token from.")
    fetch_parser.add_argument("-o", "--output", type=Path, help="Write payload to a file instead of stdout.")
    fetch_parser.add_argument(
        "--format",
        dest="format_name",
        choices=("markdown", "json"),
        default="markdown",
        help="Payload format. Default: markdown.",
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
    fetch_parser.add_argument("--comments", action="store_true", help="Append a # Discussion section.")
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
    fetch_parser.add_argument("--verbose", action="store_true", help="Write detailed diagnostics to stderr.")
    fetch_parser.add_argument("--no-progress", action="store_true", help="Disable progress output on stderr.")

    config_parser = subparsers.add_parser("config", help="Show or update non-secret config.")
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
    return parser


def normalize_argv(argv: Sequence[str]) -> list[str]:
    args = list(argv)
    if not args:
        return args
    first = args[0]
    if first in {"fetch", "config"}:
        return args
    if first.startswith("-"):
        return args
    if first.startswith(("http://", "https://")):
        return ["fetch", *args]
    return args


def validate_fetch_args(args: argparse.Namespace) -> None:
    if args.assets_dir and not args.download_images:
        raise UsageError("--assets-dir requires --download-images.")
    if (args.comment_limit != 10 or args.comment_kinds != "all") and not args.comments:
        raise UsageError("--comment-limit and --comment-kinds require --comments.")
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
    active_env = env if env is not None else dict(os.environ)
    parser = build_parser()

    try:
        parsed_argv = normalize_argv(list(argv) if argv is not None else sys.argv[1:])
        args = parser.parse_args(parsed_argv)
        if args.command == "fetch":
            return run_fetch(args, stdout=active_stdout, stderr=active_stderr, env=active_env, home=home)
        if args.command == "config":
            return run_config(args, stdout=active_stdout, stderr=active_stderr, env=active_env, home=home)
        raise UsageError("A command is required.")
    except AppError as exc:
        active_stderr.write(f"Error: {exc}\n")
        return exc.exit_code
