import contextlib
import io
import json
from pathlib import Path

import pytest

from confluence_fetch import cli, skill
from confluence_fetch.skill_content import render_skill


def old_skill():
    path = skill.skill_dir() / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_skill("0.9").encode())
    return path


def invoke(argv, **kwargs):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = cli.main(argv, stdout=stdout, stderr=stderr, env={}, **kwargs)
        except SystemExit as exc:
            code = exc.code
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.mark.parametrize("argv", [
    [], ["--help"], ["-h"], ["--version"], ["-v"], ["--about"],
    ["fetch", "--help"], ["config", "--help"], ["config", "show"],
])
def test_normal_invocations_synchronize_before_early_exits(installed_cli, argv):
    path = old_skill()
    code, stdout, stderr = invoke(argv)
    assert code == 0
    assert stdout
    assert "Updated skill 0.9 -> " + cli.__version__ in stderr
    assert path.read_bytes() == render_skill(cli.__version__).encode()


@pytest.mark.parametrize("argv", [
    ["skill", "install"], ["skill", "remove"], ["skill", "status"],
    ["install-skill"], ["remove-skill"], ["skill", "--help"],
    ["skill", "install", "--help"], ["skill", "remove", "--help"],
    ["skill", "status", "--help"], ["install-skill", "--help"],
    ["remove-skill", "--help"], ["--about", "skill", "status"],
])
def test_skill_management_never_calls_synchronization(monkeypatch, argv):
    def forbidden(**kwargs):
        pytest.fail("skill command called automatic synchronization")

    monkeypatch.setattr(cli, "synchronize_skill", forbidden)
    old_skill()
    code, _, stderr = invoke(argv)
    assert code == 0
    assert stderr == ""


@pytest.mark.parametrize("format_name", ["json", "text"])
def test_status_formats_and_read_only_behavior(installed_cli, format_name):
    path = old_skill()
    before = path.read_bytes()
    code, stdout, stderr = invoke(["skill", "status", "--format", format_name])
    assert code == 0
    assert not stderr
    assert path.read_bytes() == before
    if format_name == "json":
        payload = json.loads(stdout)
        assert payload["path"] == str(path)
        assert payload["installed"] and payload["managed"]
        assert payload["cli_version"] == cli.__version__
        assert payload["managed_version"] == "0.9"
        assert payload["version_relation"] == "older"
        assert payload["integrity"] == "valid"
        assert payload["auto_sync_eligible"]
        assert not payload["local_development"]
    else:
        assert "Version relation: older" in stdout
        assert "Integrity: valid" in stdout
        assert "Auto sync eligible: true" in stdout


@pytest.mark.parametrize("command", [["skill", "install"], ["install-skill"]])
def test_install_force_cli_and_json_contract(command):
    path = old_skill()
    path.write_bytes(path.read_bytes() + b"User edits\n")
    code, stdout, stderr = invoke(command)
    assert code == 2
    assert not stdout
    assert skill.FORCE_INSTALL_COMMAND in stderr
    code, stdout, stderr = invoke([*command, "--force"])
    assert code == 0
    assert json.loads(stdout) == {
        "installed": True, "updated": True, "skill": skill.SKILL_NAME, "path": str(path),
    }
    assert not stderr


@pytest.mark.parametrize("failure", [False, True])
def test_json_fetch_stdout_stays_valid_when_sync_updates_or_fails(installed_cli, monkeypatch, failure):
    path = old_skill()
    before = path.read_bytes()

    def fake_fetch(args, *, stdout, **kwargs):
        cli.write_json_payload({"page": {"id": "123"}}, stdout)
        return 0

    monkeypatch.setattr(cli, "run_fetch", fake_fetch)
    if failure:
        def fail(*args):
            raise PermissionError("replacement denied")
        monkeypatch.setattr(skill.os, "replace", fail)
    code, stdout, stderr = invoke(["fetch", "https://example.atlassian.net/wiki/pages/123", "--format", "json"])
    assert code == 0
    assert json.loads(stdout) == {"page": {"id": "123"}}
    assert ("Warning:" if failure else "Updated skill") in stderr
    if failure:
        assert path.read_bytes() == before


def test_sync_failure_preserves_primary_error_status(installed_cli, monkeypatch):
    old_skill()

    def fail(*args):
        raise OSError("disk error")

    monkeypatch.setattr(skill.os, "replace", fail)
    code, stdout, stderr = invoke(["fetch", "https://example.atlassian.net/wiki/pages/123"])
    assert code == 2
    assert not stdout
    assert "Warning:" in stderr and "Token env var" in stderr


def test_skill_commands_honor_injected_home_and_custom_directory(tmp_path):
    injected = tmp_path / "injected"
    code, stdout, stderr = invoke(["skill", "install"], home=injected)
    path = Path(json.loads(stdout)["path"])
    assert code == 0 and not stderr
    assert path == skill.default_skills_dir(injected) / skill.SKILL_NAME / "SKILL.md"
    custom = tmp_path / "custom"
    code, stdout, stderr = invoke(["skill", "install", "--skills-dir", str(custom)])
    assert code == 0 and not stderr
    code, stdout, stderr = invoke(["skill", "status", "--skills-dir", str(custom)])
    assert code == 0 and not stderr
    assert json.loads(stdout)["location"] == "custom"
    assert not json.loads(stdout)["auto_sync_eligible"]


@pytest.mark.parametrize("command", [["skill", "install"], ["install-skill"], ["skill", "remove"], ["remove-skill"]])
def test_help_documents_force(command):
    code, stdout, stderr = invoke([*command, "--help"])
    assert code == 0 and not stderr
    assert "--force" in stdout and "--skills-dir" in stdout


def test_status_parse_failure_uses_cli_error_model():
    path = old_skill()
    path.write_bytes(b"---\nmetadata: [\n---\n")
    code, stdout, stderr = invoke(["skill", "status"])
    assert code == 2
    assert not stdout
    assert "Error:" in stderr
