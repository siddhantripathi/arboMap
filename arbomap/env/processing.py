"""Environmental data processing and lag matrix creation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Any


class EnvProcessingError(RuntimeError):
    """Raised when environmental processing fails."""


def build_data_combined_via_r(config_path: str, output_dir: str) -> Path:
    """Use the R pipeline to build data_combined and return the RDS path."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        "Rscript",
        "scripts/build_data_combined.R",
        config_path,
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise EnvProcessingError(
            f"R build failed:\n{result.stdout}\n{result.stderr}"
        )

    rds_path = _find_data_combined_rds(output_path)
    if rds_path is None:
        raise EnvProcessingError("data_combined RDS was not created.")
    return rds_path


def load_data_combined_rds(rds_path: Path):
    """Load data_combined from an RDS file using pyreadr."""
    try:
        import pyreadr
    except ImportError as exc:  # pragma: no cover
        raise EnvProcessingError("pyreadr is required to read RDS files.") from exc

    result = pyreadr.read_r(str(rds_path))
    if len(result) == 0:
        raise EnvProcessingError("No objects found in RDS file.")
    return next(iter(result.values()))


def process_weather(inputs: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Placeholder for Python-native weather processing."""
    raise NotImplementedError(
        "Python-native weather processing is not implemented yet."
    )


def _find_data_combined_rds(output_path: Path) -> Path | None:
    candidates = list(output_path.glob("*data_combined*.rds"))
    if not candidates:
        return None
    # pick most recent
    return max(candidates, key=lambda p: p.stat().st_mtime)

