from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pytest
import yaml

import confluence_fetch.skill as skill
from confluence_fetch import __version__
from confluence_fetch.errors import UsageError
from confluence_fetch.skill_content import render_skill
from confluence_fetch.skill_metadata import content_digest, integrity_state, parse_metadata


def write_skill(root: Path, text: str) -> Path:
    path = root / skill.SKILL_NAME / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def sync() -> str:
    stderr = io.StringIO()
    skill.synchronize_skill(stderr=stderr)
    return stderr.getvalue()


def test_install_contains_version_metadata_and_independently_verified_hash(tmp_path):
    result = skill.install_skill(tmp_path)
    path = Path(result["path"])
    content = path.read_bytes()
    text = content.decode("utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])
    metadata = front["metadata"]
    assert front["name"] == "confluence-fetch"
    assert front["description"]
    assert "version" not in front
    assert metadata["managed-by"] == "confluence-fetch"
    assert metadata["managed-version"] == __version__
    assert f'managed-version: "{__version__}"' in text
    digest = metadata["managed-content-sha256"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    empty = text.replace(f'managed-content-sha256: "{digest}"', 'managed-content-sha256: ""', 1)
    assert digest == "sha256:" + hashlib.sha256(empty.encode("utf-8")).hexdigest()
    assert b"\r" not in content
    assert not content.startswith(b"\xef\xbb\xbf")
    assert content.endswith(b"\n")
    assert skill.MANAGED_MARKER not in text
    before = path.stat().st_mtime_ns
    assert not skill.install_skill(tmp_path)["updated"]
    assert path.stat().st_mtime_ns == before
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_integrity_normalizes_newlines(newline):
    text = render_skill(__version__).replace("\n", newline)
    parsed = parse_metadata(text)
    assert integrity_state(text, parsed) == "valid"
    assert content_digest(text, parsed) == parsed.content_hash


@pytest.mark.parametrize("old,new", [
    ("# Confluence Fetch", "# Edited Fetch"),
    ("name: confluence-fetch", "name: changed"),
    ("description: Use", "description: Always use"),
    ('managed-version: "1.0.0"', 'managed-version: "0.9.0"'),
    ("metadata:\n", "metadata:\n  author: someone\n"),
    ("## Setup", "##  Setup"),
])
def test_hash_covers_body_front_matter_and_formatting(old, new):
    text = render_skill("1.0.0").replace(old, new)
    assert integrity_state(text, parse_metadata(text)) == "altered"


def test_hash_replaces_only_metadata_scalar_without_reserializing_yaml():
    text = '''---
name: confluence-fetch
description: "Unicode café"
metadata: {author: 'A', managed-by: confluence-fetch, managed-version: '0.9', "managed-content-sha256": ""} # keep this
---
managed-content-sha256: "body example"
'''
    digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    text = text.replace('"managed-content-sha256": ""', f'"managed-content-sha256": "{digest}"')
    assert integrity_state(text, parse_metadata(text)) == "valid"


@pytest.mark.parametrize("directory_exists", [False, True])
def test_automatic_sync_does_not_install_missing_skill(installed_cli, directory_exists):
    target = skill.skill_dir()
    if directory_exists:
        target.mkdir(parents=True)
    assert sync() == ""
    assert not (target / "SKILL.md").exists()
    assert target.exists() == directory_exists


@pytest.mark.parametrize("text", [
    "custom instructions\n",
    "---\nname: confluence-fetch\n---\ncustom\n",
    f"---\nmetadata:\n  managed-by: another-tool\n---\n{skill.MANAGED_MARKER}\n",
    f"---\nmetadata:\n  managed-by: null\n---\n{skill.MANAGED_MARKER}\n",
])
def test_unmanaged_skills_are_never_overwritten(installed_cli, text):
    path = write_skill(skill.default_skills_dir(), text)
    assert sync() == ""
    for force in (False, True):
        with pytest.raises(UsageError, match="unmanaged"):
            skill.install_skill(force=force)
    assert path.read_bytes() == text.encode()
    with pytest.raises(UsageError):
        skill.remove_skill()


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_pristine_older_skill_updates_using_its_own_hash(installed_cli, newline):
    path = write_skill(skill.default_skills_dir(), render_skill("0.9.0").replace("\n", newline))
    notice = sync()
    assert "0.9.0 -> " + __version__ in notice
    assert str(path) in notice
    assert len(notice.splitlines()) == 1
    assert path.read_bytes() == render_skill(__version__).encode()


@pytest.mark.parametrize("damage,integrity", [
    ("body", "altered"), ("missing", "missing"), ("malformed", "malformed"),
    ("mismatch", "altered"), ("uppercase", "malformed"),
])
def test_altered_older_skill_requires_force(installed_cli, damage, integrity):
    text = render_skill("0.9.0")
    if damage == "body":
        text += "User instructions\n"
    elif damage == "missing":
        text = re.sub(r"^  managed-content-sha256:.*\n", "", text, flags=re.M)
    else:
        replacement = {"malformed": "bad", "mismatch": "sha256:" + "0" * 64, "uppercase": "sha256:" + "A" * 64}[damage]
        text = re.sub(r"sha256:[0-9a-f]{64}", replacement, text)
    path = write_skill(skill.default_skills_dir(), text)
    assert skill.inspect_skill(path).integrity == integrity
    assert skill.FORCE_INSTALL_COMMAND in sync()
    assert path.read_bytes() == text.encode()
    status = skill.skill_status()
    assert status["force_install_command"] == skill.FORCE_INSTALL_COMMAND
    assert status["auto_sync_eligible"] is False
    with pytest.raises(UsageError, match="skill install --force"):
        skill.install_skill()
    assert path.read_bytes() == text.encode()
    assert skill.install_skill(force=True)["updated"]
    assert path.read_bytes() == render_skill(__version__).encode()


@pytest.mark.parametrize("installed,current,relation", [
    ("1.0.0", "1.0.0", "equal"), ("1.0", "1.0.0", "equal"),
    ("2.0.0", "1.0.0", "newer"), ("1.10", "1.9", "newer"),
    ("1.9", "1.10", "older"), ("1.0rc1", "1.0", "older"),
    ("1.0.post1", "1.0", "newer"), ("1!1.0", "2.0", "newer"),
    ("1.0.dev1", "1.0a1", "older"), ("1.0+local", "1.0", "newer"),
])
def test_pep440_version_ordering(installed_cli, monkeypatch, installed, current, relation):
    monkeypatch.setattr(skill, "__version__", current)
    text = render_skill(installed)
    path = write_skill(skill.default_skills_dir(), text)
    before = path.stat().st_mtime_ns
    assert skill.skill_status()["version_relation"] == relation
    notice = sync()
    if relation == "older":
        assert path.read_bytes() == render_skill(current).encode()
        assert notice
    else:
        assert notice == ""
        assert path.stat().st_mtime_ns == before
        assert path.read_bytes() == text.encode()
        assert not skill.install_skill()["updated"]
        if relation == "newer":
            assert not skill.install_skill(force=True)["updated"]


@pytest.mark.parametrize("version", [__version__, "99.0"])
def test_equal_and_newer_altered_skills_are_quiet_during_sync(installed_cli, version):
    text = render_skill(version) + "User edits\n"
    path = write_skill(skill.default_skills_dir(), text)
    assert sync() == ""
    assert path.read_bytes() == text.encode()


@pytest.mark.parametrize("version_line", ["", '  managed-version: "invalid"\n', "  managed-version: 1\n"])
def test_managed_missing_or_malformed_version_recovers_before_hash_check(installed_cli, version_line):
    text = f"---\nname: confluence-fetch\nmetadata:\n  managed-by: confluence-fetch\n{version_line}---\nold modified body\n"
    path = write_skill(skill.default_skills_dir(), text)
    assert skill.skill_status()["recovery_required"]
    assert sync()
    assert path.read_bytes() == render_skill(__version__).encode()


def test_legacy_without_version_migrates_as_zero(installed_cli):
    path = write_skill(skill.default_skills_dir(), f"---\nname: confluence-fetch\n---\n{skill.MANAGED_MARKER}\nlegacy\n")
    status = skill.skill_status()
    assert status["managed_version"] == "0"
    assert status["integrity"] == "legacy"
    assert status["auto_sync_eligible"] is True
    assert "0 -> " + __version__ in sync()
    assert path.read_bytes() == render_skill(__version__).encode()


def test_invalid_running_version_skips_automatic_sync(installed_cli, monkeypatch):
    path = write_skill(skill.default_skills_dir(), render_skill("0.9"))
    monkeypatch.setattr(skill, "__version__", "not-a-version")
    before = path.read_bytes()
    assert sync() == ""
    assert path.read_bytes() == before
    assert not skill.skill_status()["auto_sync_eligible"]


@pytest.mark.parametrize("reason", ["local source installation", "editable installation", "unknown source"])
def test_development_skip_still_allows_explicit_install(monkeypatch, reason):
    monkeypatch.setattr(skill, "local_development_reason", lambda: reason)
    path = write_skill(skill.default_skills_dir(), render_skill("0.9"))
    before = path.read_bytes()
    assert sync() == ""
    assert path.read_bytes() == before
    status = skill.skill_status()
    assert status["local_development"]
    assert status["local_development_reason"] == reason
    assert not status["auto_sync_eligible"]
    assert skill.install_skill()["updated"]
    assert path.read_bytes() == render_skill(__version__).encode()


def test_custom_location_is_explicit_only(installed_cli, tmp_path):
    custom = tmp_path / "custom"
    path = write_skill(custom, render_skill("0.9"))
    before = path.read_bytes()
    assert sync() == ""
    assert path.read_bytes() == before
    assert not skill.skill_dir().exists()
    status = skill.skill_status(custom)
    assert status["location"] == "custom"
    assert status["path"] == str(path)
    assert not status["auto_sync_eligible"]
    assert skill.install_skill(custom)["updated"]
    assert skill.remove_skill(custom)["removed"]


def test_status_is_read_only_and_reports_missing(installed_cli):
    status = skill.skill_status()
    assert status["path"] == str(skill.skill_dir() / "SKILL.md")
    assert status["location"] == "standard"
    assert not status["installed"]
    assert not status["managed"]
    assert status["cli_version"] == __version__
    assert status["managed_version"] is None
    assert status["integrity"] == "not_applicable"
    assert not status["auto_sync_eligible"]
    assert not skill.default_skills_dir().exists()
    path = write_skill(skill.default_skills_dir(), render_skill("0.9"))
    before = path.stat().st_mtime_ns
    assert skill.skill_status()["auto_sync_eligible"]
    assert path.stat().st_mtime_ns == before


def test_atomic_replacement_exposes_complete_closed_file(installed_cli, monkeypatch):
    path = write_skill(skill.default_skills_dir(), render_skill("0.9"))
    before = path.read_bytes()
    replace = skill.os.replace
    replacements = []

    def observe(source, destination):
        assert Path(source).parent == path.parent
        assert Path(destination) == path
        assert path.read_bytes() == before
        assert Path(source).read_bytes() == render_skill(__version__).encode()
        with Path(source).open("r+b"):
            pass
        replace(source, destination)
        replacements.append(destination)

    monkeypatch.setattr(skill.os, "replace", observe)
    assert sync()
    assert replacements == [path]
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("change", ["newer", "altered", "removed"])
def test_revalidation_preserves_concurrent_changes(installed_cli, monkeypatch, change):
    path = write_skill(skill.default_skills_dir(), render_skill("0.9"))
    read = skill._read_skill
    reads = []

    def concurrent_read(selected):
        reads.append(selected)
        if len(reads) == 2:
            if change == "removed":
                path.unlink()
            else:
                text = render_skill("99.0") if change == "newer" else "User replaced the skill\n"
                path.write_bytes(text.encode())
        return read(selected)

    monkeypatch.setattr(skill, "_read_skill", concurrent_read)
    assert sync() == ""
    if change == "removed":
        assert not path.exists()
    else:
        expected = render_skill("99.0") if change == "newer" else "User replaced the skill\n"
        assert path.read_bytes() == expected.encode()
    assert not list(path.parent.glob("*.tmp"))


def test_atomic_failure_cleans_temp_file_and_keeps_original(installed_cli, monkeypatch):
    path = write_skill(skill.default_skills_dir(), render_skill("0.9"))
    before = path.read_bytes()

    def fail(*args):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(skill.os, "replace", fail)
    assert "Warning:" in sync()
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("text", [
    "---\nmetadata: [\n---\n",
    "---\nmetadata:\n  managed-by: confluence-fetch\n  managed-by: other\n---\n",
    "---\nname: missing closing delimiter\n",
])
def test_ambiguous_or_unparseable_yaml_is_preserved(installed_cli, text):
    path = write_skill(skill.default_skills_dir(), text)
    assert "Warning:" in sync()
    assert path.read_bytes() == text.encode()


@pytest.mark.parametrize("legacy", [False, True])
def test_removal_understands_both_management_formats(tmp_path, legacy):
    text = skill.MANAGED_MARKER if legacy else render_skill(__version__)
    write_skill(tmp_path, text)
    assert skill.remove_skill(tmp_path)["removed"]
    assert not (tmp_path / skill.SKILL_NAME).exists()
    assert not skill.remove_skill(tmp_path)["removed"]


@pytest.mark.parametrize("force", [False, True])
def test_install_and_removal_preserve_unrelated_files(tmp_path, force):
    path = write_skill(tmp_path, render_skill("0.9"))
    unrelated = path.parent / "notes.txt"
    unrelated.write_text("user notes", encoding="utf-8")
    skill.install_skill(tmp_path, force=force)
    skill.remove_skill(tmp_path, force=force)
    assert not path.exists()
    assert unrelated.read_text() == "user notes"


def test_unexpected_directory_contents_are_preserved(tmp_path):
    target = tmp_path / skill.SKILL_NAME
    target.mkdir()
    (target / "notes.txt").write_text("notes")
    for force in (False, True):
        with pytest.raises(UsageError):
            skill.install_skill(tmp_path, force=force)
        with pytest.raises(UsageError):
            skill.remove_skill(tmp_path, force=force)
    assert (target / "notes.txt").read_text() == "notes"


def test_non_file_skill_is_preserved(tmp_path):
    path = tmp_path / skill.SKILL_NAME / "SKILL.md"
    path.mkdir(parents=True)
    for operation in (skill.install_skill, skill.remove_skill, skill.skill_status):
        with pytest.raises(UsageError, match="regular file"):
            operation(tmp_path)
    assert path.is_dir()
