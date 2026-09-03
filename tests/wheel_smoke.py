"""Offline integration smoke test for a built wheel and development installs.

Run with: uv run --extra dev python tests/wheel_smoke.py dist/PACKAGE.whl
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    wheel = Path(sys.argv[1]).resolve(strict=True)
    scratch_root = REPO_ROOT / ".tmp"
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-wheel-smoke-", dir=scratch_root) as temporary:
        scratch = Path(temporary)
        home = scratch / "home"
        home.mkdir()
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("VIRTUAL_ENV", None)
        env.update(HOME=str(home), USERPROFILE=str(home), UV_OFFLINE="1", UV_NO_PROGRESS="1")

        def run(*args: str) -> subprocess.CompletedProcess:
            result = subprocess.run(args, cwd=scratch, env=env, capture_output=True, text=True, encoding="utf-8")
            if result.returncode:
                raise AssertionError(f"Command failed: {args}\n{result.stdout}\n{result.stderr}")
            return result

        environment = scratch / "venv"
        run("uv", "venv", "--offline", "--python", sys.executable, str(environment))
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = str(scripts / ("python.exe" if os.name == "nt" else "python"))
        command = str(scripts / ("confluence-fetch.exe" if os.name == "nt" else "confluence-fetch"))
        run("uv", "pip", "install", "--offline", "--python", python, str(wheel))

        def probe() -> dict:
            return json.loads(run(python, "-c", """
import json
from importlib.metadata import version
from confluence_fetch import __version__
from confluence_fetch.runtime import local_development_reason
print(json.dumps({
    "cli_version": __version__,
    "distribution_version": version("confluence-fetch"),
    "development": local_development_reason(),
}))
""").stdout)

        installed = probe()
        assert installed["development"] is None, installed
        version = installed["cli_version"]
        assert version == installed["distribution_version"]
        assert run(command, "--version").stdout.strip() == version
        path = home / ".agents" / "skills" / "confluence-fetch" / "SKILL.md"
        assert not path.exists(), "Version output installed a missing skill"
        assert json.loads(run(command, "skill", "install").stdout)["installed"]

        def seed_old_skill() -> bytes:
            run(python, "-c", """
from confluence_fetch.skill import skill_dir
from confluence_fetch.skill_content import render_skill
(skill_dir() / "SKILL.md").write_bytes(render_skill("0").encode("utf-8"))
""")
            return path.read_bytes()

        seed_old_skill()
        updated = run(command, "--about")
        assert f"Updated skill 0 -> {version}" in updated.stderr
        status = json.loads(run(command, "skill", "status").stdout)
        assert status["managed_version"] == version
        assert status["integrity"] == "valid"
        assert status["version_relation"] == "equal"
        assert not status["local_development"]
        assert list(path.parent.iterdir()) == [path]
        assert b"\r" not in path.read_bytes()
        assert b"uvx confluence-fetch" in path.read_bytes()
        print("Installed wheel: version, canonical skill, integrity, and automatic synchronization passed.", flush=True)

        for editable in (False, True):
            options = ["--editable"] if editable else []
            run(
                "uv", "pip", "install", "--offline", "--python", python,
                "--reinstall-package", "confluence-fetch", "--no-deps", *options, str(REPO_ROOT),
            )
            development = probe()
            assert development["development"] is not None, development
            before = seed_old_skill()
            assert run(command, "--help").stderr == ""
            assert path.read_bytes() == before
            status = json.loads(run(command, "skill", "status").stdout)
            assert status["local_development"]
            assert not status["auto_sync_eligible"]
            assert json.loads(run(command, "skill", "install").stdout)["updated"]
            assert json.loads(run(command, "skill", "status").stdout)["integrity"] == "valid"
            label = "Editable installation" if editable else "Local source installation"
            print(f"{label}: automatic skip and explicit installation passed.", flush=True)


if __name__ == "__main__":
    main()
