"""Run the local-only desktop app stub."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arbomap.app.desktop import launch_app


if __name__ == "__main__":
    launch_app()

