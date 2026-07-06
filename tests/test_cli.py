from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

import confluence_fetch.cli as cli
from confluence_fetch.models import AssetsResult, DiscussionResult, PageResult


def fake_page_result() -> PageResult:
    return PageResult(
        page_id="123456789",
        title="Example",
        url="https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        site="https://example.atlassian.net",
        body_markdown="Body",
        document_markdown="# 123456789 Example\n\n# Page\nBody",
        discussion=DiscussionResult(included=False, markdown=None),
        assets=AssetsResult(downloaded=False, directory=None, files=[]),
    )


def test_fetch_requires_assets_flag_for_assets_dir(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        [
            "fetch",
            "--assets-dir",
            str(tmp_path / "assets"),
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token"},
        home=tmp_path,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "--assets-dir requires --download-images" in stderr.getvalue()


def test_fetch_comment_flags_require_comments(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        [
            "fetch",
            "--comment-limit",
            "5",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token"},
        home=tmp_path,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "--comment-limit, --comment-kinds, and --comment-order require --comments" in stderr.getvalue()


def test_fetch_writes_payload_to_stdout_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "fetch_document", lambda *args, **kwargs: fake_page_result())
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token", "CONFLUENCE_EMAIL": "user@example.com"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert stdout.getvalue().startswith("# 123456789 Example")
    assert stderr.getvalue() == ""


def test_main_reconfigures_standard_streams_to_utf8(monkeypatch, tmp_path: Path) -> None:
    result = fake_page_result()
    result.document_markdown = "# 123456789 Example\n\n# Page\nUTF-8: ✅"
    monkeypatch.setattr(cli, "fetch_document", lambda *args, **kwargs: result)
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        env={"CONFLUENCE_TOKEN": "token", "CONFLUENCE_EMAIL": "user@example.com"},
        home=tmp_path,
    )

    assert exit_code == 0
    stdout.flush()
    assert "UTF-8: ✅" in stdout_bytes.getvalue().decode("utf-8")
    assert stderr_bytes.getvalue() == b""


def test_fetch_output_file_keeps_stdout_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "fetch_document", lambda *args, **kwargs: fake_page_result())
    stdout = io.StringIO()
    stderr = io.StringIO()
    output_path = tmp_path / "page.md"

    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "-o",
            str(output_path),
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token", "CONFLUENCE_EMAIL": "user@example.com"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert stdout.getvalue() == ""
    assert output_path.read_text(encoding="utf-8").startswith("# 123456789 Example")
    assert stderr.getvalue() == ""


def test_config_show_goes_to_stdout(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        ["config", "show"],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert "Config path:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_url_only_defaults_to_fetch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "fetch_document", lambda *args, **kwargs: fake_page_result())
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        ["https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example"],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token", "CONFLUENCE_EMAIL": "user@example.com"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert stdout.getvalue().startswith("# 123456789 Example")
    assert stderr.getvalue() == ""


def test_fetch_uses_lowercase_email_env_for_compatibility(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_fetch(url, options, **kwargs):
        captured["auth_email"] = options.auth_email
        return fake_page_result()

    monkeypatch.setattr(cli, "fetch_document", fake_fetch)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token", "confluence_email": "user@example.com"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert captured["auth_email"] == "user@example.com"


def test_fetch_prefers_config_email_over_env(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_fetch(url, options, **kwargs):
        captured["auth_email"] = options.auth_email
        return fake_page_result()

    monkeypatch.setattr(cli, "fetch_document", fake_fetch)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        ["config", "set-email", "config@example.com"],
        stdout=stdout,
        stderr=stderr,
        env={},
        home=tmp_path,
    )
    assert exit_code == 0

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token", "CONFLUENCE_EMAIL": "env@example.com"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert captured["auth_email"] == "config@example.com"


def test_fetch_prefers_domain_email_over_default(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_fetch(url, options, **kwargs):
        captured["auth_email"] = options.auth_email
        return fake_page_result()

    monkeypatch.setattr(cli, "fetch_document", fake_fetch)
    stdout = io.StringIO()
    stderr = io.StringIO()

    assert cli.main(
        ["config", "set-email", "default@example.com"],
        stdout=stdout,
        stderr=stderr,
        env={},
        home=tmp_path,
    ) == 0

    stdout = io.StringIO()
    stderr = io.StringIO()
    assert cli.main(
        ["config", "set-domain-email", "example.atlassian.net", "domain@example.com"],
        stdout=stdout,
        stderr=stderr,
        env={},
        home=tmp_path,
    ) == 0

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token"},
        home=tmp_path,
    )

    assert exit_code == 0
    assert captured["auth_email"] == "domain@example.com"


def test_fetch_requires_email_for_basic_auth(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "fetch_document", lambda *args, **kwargs: fake_page_result())
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(
        [
            "fetch",
            "--no-progress",
            "https://example.atlassian.net/wiki/spaces/ENG/pages/123456789/Example",
        ],
        stdout=stdout,
        stderr=stderr,
        env={"CONFLUENCE_TOKEN": "token"},
        home=tmp_path,
    )

    assert exit_code == 2
    assert "config set-email" in stderr.getvalue()


def test_root_help_emphasizes_url_only_happy_path() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(["--help"], stdout=stdout, stderr=stderr, env={})

    assert exit_code == 0
    help_text = stdout.getvalue()
    assert "Happy path:" in help_text
    assert "confluence-fetch <url>" in help_text
    assert 'automatically treats it as "fetch <url>"' in help_text
    assert "config set-email you@example.com" in help_text
    assert "install-skill" in help_text
    assert "remove-skill" in help_text
    assert "--comments" in help_text
    assert "--comment-limit N" in help_text
    assert "--comment-kinds all|footer|inline" in help_text
    assert "--comment-order created|updated|document" in help_text
    assert "read:page:confluence" in help_text
    assert "read:comment:confluence" in help_text
    assert "read:attachment:confluence" in help_text
    assert "read:user:confluence" in help_text
    assert "Project:\n  https://github.com/pseudosavant/confluence-fetch" in help_text
    assert "License:\n  MIT" in help_text
    assert stderr.getvalue() == ""


def test_no_args_shows_help_and_returns_zero() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main([], stdout=stdout, stderr=stderr, env={})

    assert exit_code == 0
    help_text = stdout.getvalue()
    assert "Happy path:" in help_text
    assert "confluence-fetch <url>" in help_text
    assert "--comments" in help_text
    assert "--comment-limit N" in help_text
    assert "--comment-kinds all|footer|inline" in help_text
    assert "--comment-order created|updated|document" in help_text
    assert "read:page:confluence" in help_text
    assert "read:comment:confluence" in help_text
    assert "read:attachment:confluence" in help_text
    assert "read:user:confluence" in help_text
    assert "Project:\n  https://github.com/pseudosavant/confluence-fetch" in help_text
    assert "License:\n  MIT" in help_text
    assert stderr.getvalue() == ""


def test_about_prints_project_and_license() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(["--about"], stdout=stdout, stderr=stderr, env={})

    assert exit_code == 0
    assert stdout.getvalue() == (
        f"confluence-fetch {cli.__version__}\n"
        "\n"
        "Agent-first CLI for fetching Confluence Cloud page context as Markdown or JSON.\n"
        "\n"
        "Project: https://github.com/pseudosavant/confluence-fetch\n"
        "License: MIT\n"
    )
    assert stderr.getvalue() == ""


def test_version_flag_prints_version_and_returns_zero() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(["--version"], stdout=stdout, stderr=stderr, env={})

    assert exit_code == 0
    assert stdout.getvalue() == f"{cli.__version__}\n"
    assert stderr.getvalue() == ""


def test_install_skill_command_outputs_json(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(["install-skill", "--skills-dir", str(tmp_path)], stdout=stdout, stderr=stderr, env={})

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["installed"] is True
    assert payload["skill"] == "confluence-fetch"
    assert (tmp_path / "confluence-fetch" / "SKILL.md").exists()
    assert stderr.getvalue() == ""


def test_remove_skill_command_outputs_json(tmp_path: Path) -> None:
    assert cli.main(["install-skill", "--skills-dir", str(tmp_path)], stdout=io.StringIO(), stderr=io.StringIO(), env={}) == 0
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.main(["remove-skill", "--skills-dir", str(tmp_path)], stdout=stdout, stderr=stderr, env={})

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["removed"] is True
    assert not (tmp_path / "confluence-fetch").exists()
    assert stderr.getvalue() == ""


def test_fetch_help_explains_url_first_usage() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["fetch", "--help"], env={})

    assert excinfo.value.code == 0
    help_text = stdout.getvalue()
    assert "Happy path:" in help_text
    assert "confluence-fetch <url>" in help_text
    assert "Most runs should only need the URL." in help_text
    assert "Bare page IDs are not supported; pass a Confluence URL" in help_text
    assert "read:page:confluence" in help_text
    assert "read:comment:confluence" in help_text
    assert "read:attachment:confluence" in help_text
    assert "read:user:confluence" in help_text
    assert "--comment-order" in help_text
    assert "Default comment order is document" in help_text
    assert stderr.getvalue() == ""
