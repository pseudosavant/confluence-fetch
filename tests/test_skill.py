from __future__ import annotations

from pathlib import Path

import pytest

from confluence_fetch.errors import UsageError
from confluence_fetch.skill import MANAGED_MARKER, SKILL_MD, install_skill, remove_skill


def test_install_skill_creates_and_updates_managed_skill(tmp_path: Path) -> None:
    first = install_skill(tmp_path)

    assert first["installed"] is True
    assert first["updated"] is True
    skill_path = tmp_path / "confluence-fetch" / "SKILL.md"
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert "name: confluence-fetch" in content
    assert "$confluence-fetch {confluence URL}" in content
    assert "uvx confluence-fetch" in content
    assert "uvx confluenc-fetch" not in content
    assert MANAGED_MARKER in content

    second = install_skill(tmp_path)
    assert second["installed"] is True
    assert second["updated"] is False


def test_install_skill_overwrites_existing_skill_content(tmp_path: Path) -> None:
    skill_dir = tmp_path / "confluence-fetch"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text("---\nname: confluence-fetch\n---\nold skill text\n", encoding="utf-8")

    result = install_skill(tmp_path)

    assert result["installed"] is True
    assert result["updated"] is True
    assert skill_path.read_text(encoding="utf-8") == SKILL_MD


def test_skill_text_is_platform_and_agent_neutral() -> None:
    assert "agentic tool" in SKILL_MD
    assert "Codex" not in SKILL_MD
    assert "powershell" not in SKILL_MD.lower()
    assert "C:\\tmp" not in SKILL_MD


def test_remove_skill_removes_only_managed_skill(tmp_path: Path) -> None:
    install_skill(tmp_path)

    removed = remove_skill(tmp_path)

    assert removed["removed"] is True
    assert not (tmp_path / "confluence-fetch").exists()


def test_remove_skill_refuses_unmanaged_skill_without_force(tmp_path: Path) -> None:
    skill_dir = tmp_path / "confluence-fetch"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: confluence-fetch\n---\ncustom\n", encoding="utf-8")

    with pytest.raises(UsageError):
        remove_skill(tmp_path)

    removed = remove_skill(tmp_path, force=True)
    assert removed["removed"] is True
