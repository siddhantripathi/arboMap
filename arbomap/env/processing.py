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
    """Load data_combined from an RDS file using rpy2 (handles matrix columns)."""
    try:
        import rpy2.robjects as robjects
        from rpy2.robjects import pandas2ri
        from rpy2.robjects import conversion
        import numpy as np
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise EnvProcessingError("rpy2, numpy, and pandas are required.") from exc

    r_data = robjects.r["readRDS"](str(rds_path))
    if r_data is None:
        raise EnvProcessingError("No object found in RDS file.")

    # Separate scalar and matrix columns
    col_names = list(r_data.names)
    scalar_cols = []
    matrix_cols = {}
    
    for col in col_names:
        col_data = r_data.rx2(col)
        # Check if column is a matrix using R's is.matrix()
        is_matrix = bool(robjects.r["is.matrix"](col_data)[0])
        if is_matrix:
            # Extract matrix as numpy array (shape: n_rows x n_cols)
            matrix = np.array(col_data)
            # Convert to Series where each element is a 2D array (1 x n_cols)
            # This matches what r_backend expects for matrix columns
            matrix_cols[col] = [matrix[i:i+1, :] for i in range(matrix.shape[0])]
        else:
            scalar_cols.append(col)
    
    # Convert scalar columns to pandas DataFrame
    if scalar_cols:
        scalar_df = r_data.rx2[scalar_cols]
        with conversion.localconverter(pandas2ri.converter):
            df = conversion.rpy2py(scalar_df)
    else:
        # If no scalar columns, create empty DataFrame with correct index
        n_rows = len(r_data.rx2[col_names[0]]) if col_names else 0
        df = pd.DataFrame(index=range(n_rows))
    
    # Add matrix columns as Series of 2D arrays
    for col_name, matrix_list in matrix_cols.items():
        df[col_name] = matrix_list
    
    return df


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

