"""R/mgcv backend via rpy2 for parity-focused modeling."""

from __future__ import annotations

from typing import Dict, Any, Tuple, List

import numpy as np
import pandas as pd


class RBackendError(RuntimeError):
    """Raised when rpy2 or R execution fails."""


def fit_bam_models(
    data_combined: pd.DataFrame,
    model_formulas: Dict[str, str],
    config: Dict[str, Any],
) -> pd.DataFrame:
    """Fit mgcv::bam models in R and return per-model predictions."""
    robjects, pandas2ri, mgcv = _load_rpy2()
    _configure_r(robjects, config)

    _require_columns(data_combined, ["arbo_ID", "any_cases"])
    
    # Convert arbo_ID to categorical before R conversion (will become R factor automatically)
    # This avoids the need for _coerce_factor which uses rx2 assignment (doesn't work)
    data_combined_fixed = data_combined.copy()
    if "arbo_ID" in data_combined_fixed.columns:
        data_combined_fixed["arbo_ID"] = pd.Categorical(data_combined_fixed["arbo_ID"].astype(str))
    
    r_df = _to_r_dataframe(robjects, pandas2ri, data_combined_fixed)

    preds = []
    subset = _build_subset(robjects, r_df, "modeled")
    for model_name, formula in model_formulas.items():
        r_formula = robjects.Formula(formula)
        r_model = mgcv.bam(
            r_formula,
            family=robjects.r["binomial"](),
            data=r_df,
            subset=subset,
        )
        r_pred = robjects.r["predict"](
            r_model, r_df, type="response"
        )
        pred = np.array(r_pred)
        preds.append(_build_pred_frame(data_combined, model_name, pred))

    return pd.concat(preds, ignore_index=True)


def _load_rpy2():
    try:
        import rpy2.robjects as robjects
        from rpy2.robjects import pandas2ri
        from rpy2.robjects.packages import importr
    except ImportError as exc:  # pragma: no cover
        raise RBackendError("rpy2 is required for the R backend.") from exc

    try:
        mgcv = importr("mgcv")
    except Exception as exc:  # pragma: no cover
        raise RBackendError("R package 'mgcv' is required.") from exc

    return robjects, pandas2ri, mgcv


def _configure_r(robjects, config: Dict[str, Any]) -> None:
    seed = (
        config.get("runtime", {}).get("random_seed", 12345)
    )
    robjects.r["set.seed"](seed)
    robjects.r["options"](mc_cores=1)


def _to_r_dataframe(robjects, pandas2ri, df: pd.DataFrame):
    # Verify input DataFrame is valid
    if df.empty:
        raise RBackendError("Input DataFrame is empty")
    if len(df) < 1:
        raise RBackendError(f"Input DataFrame has invalid row count: {len(df)}")
    
    scalar_df, matrices = _split_scalar_and_matrix(df)
    from rpy2.robjects import conversion

    # Use original DataFrame length - conversion might alter row count
    n_rows = len(df)
    scalar_rows = len(scalar_df)
    
    # Debug output to trace row count
    print(f"DEBUG _to_r_dataframe: Input df shape: {df.shape}")
    print(f"DEBUG _to_r_dataframe: scalar_df shape: {scalar_df.shape}")
    print(f"DEBUG _to_r_dataframe: Number of matrices: {len(matrices)}")
    if matrices:
        first_matrix_name = list(matrices.keys())[0]
        print(f"DEBUG _to_r_dataframe: First matrix '{first_matrix_name}' shape: {matrices[first_matrix_name].shape}")
    
    # Debug: Check if scalar_df already has wrong row count
    if scalar_rows != n_rows:
        raise RBackendError(
            f"Scalar DataFrame has wrong row count: expected {n_rows}, got {scalar_rows}. "
            f"This suggests an issue in data loading or matrix column separation."
        )

    # Reset index to ensure all rows are preserved during conversion
    # pandas2ri might have issues with non-contiguous or duplicate indices
    scalar_df_reset = scalar_df.reset_index(drop=True)
    
    # Convert scalar columns to R data frame first
    with conversion.localconverter(pandas2ri.converter):
        r_df = conversion.py2rpy(scalar_df_reset)
    
    # Verify converted R data frame has correct row count
    r_df_rows = len(r_df)
    if r_df_rows != n_rows:
        raise RBackendError(
            f"R data frame conversion lost rows: expected {n_rows}, got {r_df_rows}. "
            f"Scalar DataFrame had {scalar_rows} rows before conversion. "
            f"This indicates pandas2ri conversion is collapsing rows - possible causes: "
            f"duplicate row removal, factor/character conversion issues, or index misalignment."
        )
    for name, matrix in matrices.items():
        # Matrix should be shape (n_rows, n_cols) for R
        if matrix.ndim != 2:
            raise RBackendError(
                f"Matrix '{name}' must be 2D, got shape {matrix.shape}"
            )
        if matrix.shape[0] != n_rows:
            raise RBackendError(
                f"Matrix '{name}' row count {matrix.shape[0]} doesn't match data frame rows {n_rows}"
            )
        
        r_matrix = robjects.r["matrix"](
            robjects.FloatVector(matrix.flatten(order="C")),
            nrow=matrix.shape[0],
            ncol=matrix.shape[1],
            byrow=False,  # R matrices are column-major by default
        )
        
        # Try using r_df[name] instead of r_df.rx2[name]
        # This should be equivalent to df$name <- matrix in R
        try:
            r_df[name] = r_matrix
        except Exception:
            # Fallback: use R's list assignment
            r_list = robjects.r["as.list"](r_df)
            r_list.rx2[name] = r_matrix
            r_df = robjects.r["as.data.frame"](r_list, check_names=False)

    return r_df


def _split_scalar_and_matrix(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
    matrices: Dict[str, np.ndarray] = {}
    scalar_cols = []
    for col in df.columns:
        value = df[col].iloc[0]
        if isinstance(value, (list, np.ndarray)):
            arr = np.asarray(value)
            if arr.ndim == 2:
                matrices[col] = _stack_matrices(df[col], col)
                continue
        scalar_cols.append(col)
    return df[scalar_cols].copy(), matrices


def _stack_matrices(series: pd.Series, col: str) -> np.ndarray:
    """Stack matrix rows into a single 2D array for R.
    
    Each element in the series should be a 2D array of shape (1, n_cols).
    The result will be shape (n_rows, n_cols) suitable for R matrix columns.
    """
    matrices = []
    shapes = set()
    for item in series.to_numpy():
        arr = np.asarray(item)
        if arr.ndim != 2:
            raise RBackendError(
                f"Matrix column '{col}' contains non-2D entries."
            )
        # Squeeze to 1D if shape is (1, n) to get (n,)
        if arr.shape[0] == 1:
            arr = arr[0, :]  # Extract row to get 1D array
        matrices.append(arr)
        shapes.add(arr.shape)
    if len(shapes) != 1:
        raise RBackendError(
            f"Matrix column '{col}' has inconsistent shapes: {sorted(shapes)}"
        )
    # Stack 1D arrays into 2D array (n_rows, n_cols)
    return np.vstack(matrices)


def _build_subset(robjects, r_df, column: str):
    if column not in r_df.names:
        return None
    return robjects.r["as.logical"](r_df.rx2(column))


def _coerce_factor(robjects, r_df, column: str):
    """DEPRECATED: Convert a column to factor in R.
    
    This function is deprecated. Convert columns to pd.Categorical in Python
    before calling _to_r_dataframe instead. They will automatically become R factors.
    
    Kept for backward compatibility but should not be used.
    """
    if column in r_df.names:
        # Use list conversion method (same as matrix columns)
        r_list = robjects.r["as.list"](r_df)
        col_values = r_df.rx2(column)
        r_factor = robjects.r["factor"](col_values)
        r_list.rx2[column] = r_factor
        return robjects.r["as.data.frame"](r_list, check_names=False)
    return r_df


def _build_pred_frame(
    data_combined: pd.DataFrame,
    model_name: str,
    pred: np.ndarray,
) -> pd.DataFrame:
    base_cols = [
        col
        for col in [
            "arbo_ID",
            "date_epi",
            "week_epi",
            "year_epi",
            "any_cases",
            "case_count",
            "observed",
            "modeled",
            "doy",
        ]
        if col in data_combined.columns
    ]
    pred_frame = data_combined[base_cols].copy()
    pred_frame["pred"] = pred
    pred_frame["model"] = model_name
    return pred_frame


def _require_columns(df: pd.DataFrame, columns: List[str]) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise RBackendError(f"Missing required columns for modeling: {missing}")
