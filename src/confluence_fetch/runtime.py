from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit


DISTRIBUTION_NAME = "confluence-fetch"


def local_development_reason() -> str | None:
    """Identify installed code using distribution provenance, never launcher paths."""
    try:
        distribution = metadata.distribution(DISTRIBUTION_NAME)
        direct_url_text = distribution.read_text("direct_url.json")
        if direct_url_text is not None:
            direct_url = json.loads(direct_url_text)
            directory = direct_url.get("dir_info", {})
            if directory.get("editable"):
                return "editable installation"
            source = urlsplit(direct_url["url"])
            if source.scheme == "file":
                # A built wheel is an installed artifact. Local source directories
                # and source archives are development builds, even when not editable.
                if "dir_info" in direct_url or not (
                    source.path.lower().endswith(".whl") and "archive_info" in direct_url
                ):
                    return "local source installation"
        runtime_init = Path(__file__).with_name("__init__.py").resolve()
        source_root = runtime_init.parent.parent
        if source_root.name == "src":
            source_root = source_root.parent
        if (source_root / "pyproject.toml").is_file() or (source_root / ".git").exists():
            return "local project checkout"
        installed_init = Path(distribution.locate_file("confluence_fetch/__init__.py")).resolve()
        if runtime_init != installed_init:
            return "local checkout or source outside the installed distribution"
    except (metadata.PackageNotFoundError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return "runtime distribution source could not be identified"
    return None
