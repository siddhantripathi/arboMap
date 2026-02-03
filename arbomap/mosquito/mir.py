"""Mosquito infection modeling and MIR imputation."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

import pandas as pd


class MirError(RuntimeError):
    """Raised when MIR outputs cannot be loaded."""


def load_mir_full(output_dir: str) -> pd.DataFrame:
    """Load MIR summary produced by the R pipeline."""
    path = Path(output_dir) / "data_combined_build_mir_full.csv"
    if not path.exists():
        raise MirError("MIR output not found. Run build_data_combined_via_r first.")
    return pd.read_csv(path)


def compute_mir(inputs: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Placeholder for Python-native MIR computation."""
    raise NotImplementedError("Python-native MIR computation is not implemented yet.")

