# Changelog

## 1.1.0 - 2026-09-03

- Synchronize existing managed skills in the standard directory to the running CLI version on ordinary invocations.
- Store management, exact version, and normalized content hash in `SKILL.md` YAML metadata. Migrate legacy markers and recover missing or malformed versions.
- Preserve modified, unverifiable, unmanaged, current, and newer skills during automatic checks. Add `uvx confluence-fetch skill install --force` for explicit managed replacements.
- Add read-only `skill status` with JSON and text output. Retain `install-skill`, `remove-skill`, and removal's `--force` option.
- Skip automatic checks for skill commands, local source builds, and editable installs. Custom locations require explicit updates.
- Replace files atomically and preserve unrelated files during removal. Maintenance notices remain on stderr and cannot fail the primary command.
- Keep skill invocation instructions on `uvx`. Synchronization does not update packages or uv caches. Changes apply when agents next load the skill.
