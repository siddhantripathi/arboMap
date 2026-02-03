"""Run full model: build data_combined via R and fit GAMs via rpy2."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arbomap.env.processing import build_data_combined_via_r, load_data_combined_rds
from arbomap.io import load_config, load_inputs
from arbomap.modeling.gam import fit_models


def main() -> None:
    config_path = str(ROOT / "config" / "default_config.yaml")
    out_dir = ROOT / "runs" / "full_model"
    print("Step 1/4: build data_combined via R...")
    rds_path = build_data_combined_via_r(config_path, str(out_dir))
    print(f"Step 1/4 complete: {rds_path}")
    print("Step 2/4: load data_combined RDS...")
    data_combined = load_data_combined_rds(rds_path)
    print(f"Step 2/4 complete: rows={len(data_combined)} cols={len(data_combined.columns)}")

    print("Step 3/4: load model formulas...")
    config = load_config(config_path)
    inputs = load_inputs(config.data)
    model_formulas = inputs["models"]
    print(f"Step 3/4 complete: {len(model_formulas)} models")

    print("Step 4/4: fit GAMs via rpy2/mgcv...")
    preds = fit_models(data_combined, model_formulas, config.data)
    out_dir.mkdir(parents=True, exist_ok=True)
    preds.to_csv(out_dir / "predictions.csv", index=False)
    print(f"Step 4/4 complete: {len(preds)} predictions")
    print(f"Wrote predictions: {out_dir / 'predictions.csv'}")


if __name__ == "__main__":
    main()

