"""Run full Python-native pipeline: preprocessing + GAM fitting."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arbomap.pipeline import run_pipeline
from arbomap.modeling.gam import fit_models
from arbomap.io import load_config, load_inputs


def main() -> None:
    config_path = str(ROOT / "config" / "default_config.yaml")
    out_dir = ROOT / "runs" / "python_pipeline"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("ArboMAP Python-Native Pipeline")
    print("=" * 60)
    
    # Run preprocessing pipeline
    print("\n[PREPROCESSING]")
    data_combined = run_pipeline(config_path, str(out_dir), verify=True)
    print(f"\n✓ Preprocessing complete: {len(data_combined)} rows")
    
    # Load model formulas
    print("\n[MODELING]")
    config = load_config(config_path)
    inputs = load_inputs(config.data)
    model_formulas = inputs["models"]
    print(f"✓ Loaded {len(model_formulas)} model formulas")
    
    # Fit GAMs
    print("\n[GAM FITTING]")
    preds = fit_models(data_combined, model_formulas, config.data)
    print(f"✓ GAM fitting complete: {len(preds)} predictions")
    
    # Save outputs
    preds.to_csv(out_dir / "predictions.csv", index=False)
    print(f"\n✓ Saved predictions: {out_dir / 'predictions.csv'}")
    
    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

