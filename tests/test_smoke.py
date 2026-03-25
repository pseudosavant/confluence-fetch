from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"


def build_env() -> dict[str, str]:
    env = dict(os.environ)
    pythonpath_parts = [str(REPO_ROOT / "src")]
    if SITE_PACKAGES.exists():
        pythonpath_parts.append(str(SITE_PACKAGES))
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def test_module_entry_point_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "confluence_fetch", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=build_env(),
        check=False,
    )

    assert result.returncode == 0
    assert "confluence-fetch" in result.stdout


def test_pep723_wrapper_help() -> None:
    result = subprocess.run(
        [sys.executable, "confluence_fetch.py", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=build_env(),
        check=False,
    )

    assert result.returncode == 0
    assert "fetch" in result.stdout
