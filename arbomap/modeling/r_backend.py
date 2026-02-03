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
    r_df = _to_r_dataframe(robjects, pandas2ri, data_combined)
    _coerce_factor(robjects, r_df, "arbo_ID")

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
    scalar_df, matrices = _split_scalar_and_matrix(df)
    from rpy2.robjects import conversion

    with conversion.localconverter(pandas2ri.converter):
        r_df = conversion.py2rpy(scalar_df)

    for name, matrix in matrices.items():
        r_matrix = robjects.r["matrix"](
            robjects.FloatVector(matrix.flatten(order="C")),
            nrow=matrix.shape[0],
            ncol=matrix.shape[1],
            byrow=True,
        )
        r_df.rx2[name] = r_matrix

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
    matrices = []
    shapes = set()
    for item in series.to_numpy():
        arr = np.asarray(item)
        if arr.ndim != 2:
            raise RBackendError(
                f"Matrix column '{col}' contains non-2D entries."
            )
        matrices.append(arr)
        shapes.add(arr.shape)
    if len(shapes) != 1:
        raise RBackendError(
            f"Matrix column '{col}' has inconsistent shapes: {sorted(shapes)}"
        )
    return np.stack(matrices)


def _build_subset(robjects, r_df, column: str):
    if column not in r_df.names:
        return None
    return robjects.r["as.logical"](r_df.rx2(column))


def _coerce_factor(robjects, r_df, column: str) -> None:
    if column in r_df.names:
        levels = robjects.r["levels"](robjects.r["factor"](r_df.rx2(column)))
        r_df.rx2[column] = robjects.r["factor"](r_df.rx2(column), levels=levels)


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
