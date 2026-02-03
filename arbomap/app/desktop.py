"""Desktop app entrypoint (local-only execution)."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path when running directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arbomap.app.ui_tk import launch_tkinter_app


def launch_app() -> None:
    """Launch the Tkinter desktop UI (local-only)."""
    launch_tkinter_app()


if __name__ == "__main__":
    launch_app()

