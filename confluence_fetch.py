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
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PACKAGE_DIR = SRC / "confluence_fetch"
if __name__ == "confluence_fetch":
    __path__ = [str(PACKAGE_DIR)]
    __package__ = "confluence_fetch"

main = importlib.import_module("confluence_fetch.cli").main


if __name__ == "__main__":
    raise SystemExit(main())
