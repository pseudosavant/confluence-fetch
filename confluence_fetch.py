#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "beautifulsoup4>=4.12",
#   "httpx>=0.27",
#   "markdownify>=0.13",
#   "tomli-w>=1.0",
# ]
# ///

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PACKAGE_DIR = SRC / "confluence_fetch"


def load_package() -> None:
    package_init = PACKAGE_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "confluence_fetch",
        package_init,
        submodule_search_locations=[str(PACKAGE_DIR)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load package from {package_init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["confluence_fetch"] = module
    spec.loader.exec_module(module)


load_package()

main = importlib.import_module("confluence_fetch.cli").main


if __name__ == "__main__":
    raise SystemExit(main())
