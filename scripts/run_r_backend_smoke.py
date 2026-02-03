"""Smoke test for rpy2 mgcv backend availability."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arbomap.modeling.r_backend import _load_rpy2


def main() -> None:
    baseline_path = ROOT / "baseline" / "outputs" / "baseline_run_predictions.csv"
    if baseline_path.exists():
        baseline = pd.read_csv(baseline_path)
        print(f"Baseline predictions rows: {len(baseline)}")
        print(f"Baseline prediction columns: {list(baseline.columns)}")
    else:
        print("Baseline predictions file not found.")

    try:
        _load_rpy2()
        print("rpy2/mgcv backend import: OK")
    except Exception as exc:  # pragma: no cover - runtime check
        print(f"rpy2/mgcv backend import: FAIL ({exc})")


if __name__ == "__main__":
    main()

