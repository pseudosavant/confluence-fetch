from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from confluence_fetch import __version__
from confluence_fetch.errors import UsageError
from confluence_fetch.runtime import local_development_reason
from confluence_fetch.skill_content import render_skill
from confluence_fetch.skill_metadata import (
    MANAGED_BY,
    MANAGED_MARKER,
    integrity_state,
    parse_metadata,
)


SKILL_NAME = "confluence-fetch"
FORCE_INSTALL_COMMAND = "uvx confluence-fetch skill install --force"


def default_skills_dir(home: Path | None = None) -> Path:
    return (home if home is not None else Path.home()) / ".agents" / "skills"


def skill_dir(skills_dir: Path | None = None) -> Path:
    return (skills_dir if skills_dir is not None else default_skills_dir()) / SKILL_NAME


def _version(value: str | None) -> Version | None:
    try:
        return Version(value) if value is not None else None
    except InvalidVersion:
        return None


@dataclass(frozen=True)
class InstalledSkill:
    content: bytes | None
    managed: bool = False
    version_text: str | None = None
    version: Version | None = None
    integrity: str = "not_applicable"
    recovery: bool = False

    def relation(self, current: Version | None) -> str:
        if not self.managed:
            return "not_applicable"
        if current is None or self.version is None:
            return "unknown"
        if self.version == current:
            return "equal"
        return "older" if self.version < current else "newer"

    def update_needed(self, current: Version | None) -> bool:
        return self.managed and current is not None and (
            self.recovery or (self.relation(current) == "older" and self.integrity == "valid")
        )


def _read_skill(path: Path) -> bytes | None:
    for target in (path.parent, path):
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            raise UsageError(f"Refusing to manage linked skill path '{target}'.")
    if path.parent.exists() and not path.parent.is_dir():
        raise UsageError(f"Skill directory '{path.parent}' is not a directory.")
    if path.exists() and not path.is_file():
        raise UsageError(f"Skill path '{path}' is not a regular file.")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def inspect_skill(path: Path) -> InstalledSkill:
    content = _read_skill(path)
    if content is None:
        return InstalledSkill(None)
    text = content.decode("utf-8")
    metadata = parse_metadata(text)
    legacy = MANAGED_MARKER in text
    managed = metadata.manager == MANAGED_BY if metadata.manager_present else legacy
    if not managed:
        return InstalledSkill(content)
    version = _version(metadata.version)
    if legacy and metadata.version is None:
        return InstalledSkill(content, True, "0", Version("0"), "legacy", True)
    return InstalledSkill(
        content, True, metadata.version if version is not None else None,
        version, integrity_state(text, metadata), version is None,
    )


def _atomic_write(path: Path, text: str, expected: bytes | None) -> bool:
    """Replace a complete file only if the observed installed bytes still match."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=".SKILL-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Exact bytes protect a newly observed newer version, edits, removal,
        # and another completed synchronization.
        if _read_skill(path) != expected:
            return False
        os.replace(temporary, path)
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_skill(skills_dir: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    path = skill_dir(skills_dir) / "SKILL.md"
    state = inspect_skill(path)
    canonical = render_skill(__version__)
    updated = False
    if state.content is None:
        if path.parent.exists() and any(path.parent.iterdir()):
            raise UsageError(f"Refusing to install into nonempty skill directory '{path.parent}' without SKILL.md.")
        path.parent.mkdir(parents=True, exist_ok=True)
        updated = True
    elif not state.managed:
        raise UsageError(f"Refusing to overwrite unmanaged skill '{path}'.")
    elif state.relation(_version(__version__)) == "newer":
        pass
    elif state.recovery:
        updated = True
    elif state.integrity != "valid" and not force:
        raise UsageError(
            f"Skill '{path}' is altered or unverifiable. Use `{FORCE_INSTALL_COMMAND}` to replace it."
            + (
                " Repeat --skills-dir for this custom location."
                if skills_dir is not None and skills_dir.absolute() != default_skills_dir().absolute() else ""
            )
        )
    elif force:
        updated = state.content != canonical.encode("utf-8")
    else:
        updated = state.update_needed(_version(__version__))
    if updated and not _atomic_write(path, canonical, state.content):
        raise UsageError(f"Skill '{path}' changed during installation. Run the command again.")
    return {"installed": True, "updated": updated, "skill": SKILL_NAME, "path": str(path)}


def remove_skill(skills_dir: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    target = skill_dir(skills_dir)
    path = target / "SKILL.md"
    content = _read_skill(path)
    if not target.exists():
        return {"removed": False, "skill": SKILL_NAME, "path": str(target), "reason": "not_installed"}
    if content is None:
        raise UsageError(f"Refusing to remove '{target}' because SKILL.md is missing.")
    if not force and not inspect_skill(path).managed:
        raise UsageError(
            f"Refusing to remove '{target}' because it is not marked as managed by confluence-fetch. "
            "Use --force to override."
        )
    if _read_skill(path) != content:
        raise UsageError(f"Skill '{path}' changed during removal. Run the command again.")
    path.unlink()
    # Unrelated files belong to the user, including on forced removal.
    if not any(target.iterdir()):
        try:
            target.rmdir()
        except OSError:
            pass
    return {"removed": True, "skill": SKILL_NAME, "path": str(target)}


def skill_status(skills_dir: Path | None = None, *, home: Path | None = None) -> dict[str, Any]:
    standard = default_skills_dir(home)
    selected = skills_dir if skills_dir is not None else standard
    path = skill_dir(selected) / "SKILL.md"
    state = inspect_skill(path)
    current = _version(__version__)
    development = local_development_reason()
    custom = selected.absolute() != standard.absolute()
    recommendation = (
        state.managed and not state.recovery and state.integrity != "valid"
        and state.relation(current) != "newer"
    )
    return {
        "skill": SKILL_NAME,
        "path": str(path),
        "location": "custom" if custom else "standard",
        "installed": state.content is not None,
        "managed": state.managed,
        "cli_version": __version__,
        "managed_version": state.version_text,
        "version_relation": state.relation(current),
        "integrity": state.integrity,
        "recovery_required": state.recovery,
        "auto_sync_eligible": not custom and development is None and state.update_needed(current),
        "local_development": development is not None,
        "local_development_reason": development,
        "force_install_command": FORCE_INSTALL_COMMAND if recommendation else None,
    }


def synchronize_skill(*, stderr: Any, home: Path | None = None) -> None:
    """Best-effort local maintenance. Never create a missing skill or fail a command."""
    try:
        if local_development_reason() is not None:
            return
        current = _version(__version__)
        if current is None:
            return
        path = skill_dir(default_skills_dir(home)) / "SKILL.md"
        state = inspect_skill(path)
        if state.update_needed(current):
            if _atomic_write(path, render_skill(__version__), state.content):
                old = state.version_text or "missing/invalid"
                stderr.write(f"Updated skill {old} -> {__version__}: {path}\n")
        elif state.relation(current) == "older" and state.integrity != "valid":
            stderr.write(
                f"Skill '{path}' is altered or unverifiable. Use `{FORCE_INSTALL_COMMAND}` to replace it.\n"
            )
    except Exception as exc:
        # Maintenance and even a failed diagnostic stream must not change the exit status.
        try:
            stderr.write(f"Warning: skill synchronization skipped: {exc}\n")
        except Exception:
            pass
