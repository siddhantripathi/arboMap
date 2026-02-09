"""Environmental data processing and lag matrix creation using R/mgcv via rpy2."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd

from arbomap.utils.logging import setup_logger, log_step, log_error_with_context


logger = setup_logger(__name__)


class EnvProcessingError(RuntimeError):
    """Raised when environmental processing fails."""


def compute_weather_anomalies(
    weather_data: pd.DataFrame,
    config: Dict[str, Any],
) -> pd.DataFrame:
    """Compute weather anomalies using R/mgcv::bam via rpy2.
    
    Args:
        weather_data: DataFrame with columns: arbo_ID, date_obs (or doy), var1, var2
        config: Configuration dict with 'predictor_var1' and 'predictor_var2'
        
    Returns:
        DataFrame with added columns: var1_anom, var2_anom, and imputed missing values
    """
    log_step(logger, "Weather Anomalization", f"Variables: {config.get('predictor_var1')}, {config.get('predictor_var2')}")
    
    try:
        import rpy2.robjects as robjects
        from rpy2.robjects import pandas2ri
        from rpy2.robjects import conversion
        from rpy2.robjects.packages import importr
    except ImportError as exc:
        raise EnvProcessingError("rpy2 and R package 'mgcv' are required.") from exc
    
    try:
        mgcv = importr("mgcv")
    except Exception as exc:
        raise EnvProcessingError("R package 'mgcv' must be installed.") from exc
    
    var1_name = config.get("predictor_var1", "tmeanc")
    var2_name = config.get("predictor_var2", "vpd")
    
    # Prepare data for R
    env_df = weather_data.copy()
    
    # Ensure doy exists
    if "doy" not in env_df.columns:
        if "date_obs" in env_df.columns:
            env_df["doy"] = pd.to_datetime(env_df["date_obs"]).dt.dayofyear
        else:
            raise EnvProcessingError("weather_data must have 'doy' or 'date_obs' column")
    
    # Ensure year exists (needed for date_obs creation if date_obs is missing)
    if "year" not in env_df.columns:
        if "date_obs" in env_df.columns:
            env_df["year"] = pd.to_datetime(env_df["date_obs"]).dt.year
        else:
            raise EnvProcessingError("weather_data must have 'year' or 'date_obs' column")
    
    # Convert arbo_ID to categorical (will become R factor automatically)
    # This must be done BEFORE converting to R to avoid rx2 assignment issues
    env_df["arbo_ID"] = pd.Categorical(env_df["arbo_ID"].astype(str))
    
    # Convert FULL DataFrame to R ONCE (not per-variable)
    # This optimizes from 2N round-trips (N variables × 2 each) to 2 round-trips total
    with conversion.localconverter(pandas2ri.converter):
        r_env = conversion.py2rpy(env_df[["arbo_ID", "doy", var1_name, var2_name]].copy())
    
    # Process both variables in R (reuse same data frame)
    predictions = {}
    for var_name in [var1_name, var2_name]:
        logger.info(f"Anomalizing {var_name}")
        
        # Set up variable for bam call (in R)
        # Use R code execution to add this_var column to the data frame
        robjects.r.assign("r_env", r_env)
        robjects.r.assign("var_name", var_name)
        # Add this_var column to r_env in R
        robjects.r("r_env$this_var <- r_env[[var_name]]")
        # Retrieve the modified data frame
        r_env = robjects.r["r_env"]
        
        # Fit bam model: this_var ~ arbo_ID + s(doy, bs="cc", by=arbo_ID)
        r_formula = robjects.Formula("this_var ~ arbo_ID + s(doy, bs='cc', by=arbo_ID)")
        env_mod = mgcv.bam(
            r_formula,
            data=r_env,
            discrete=True,
        )
        
        # Predict in R
        r_preds = robjects.r["predict"](env_mod, newdata=r_env)
        predictions[var_name] = np.array(r_preds)
    
    # Get all results back to Python at once
    with conversion.localconverter(pandas2ri.converter):
        r_result = conversion.rpy2py(r_env)
    
    # Build complete result DataFrame in Python
    # Preserve all original columns needed for downstream processing
    result_cols = ["arbo_ID", "doy"]
    if "year" in env_df.columns:
        result_cols.append("year")
    if "date_obs" in env_df.columns:
        result_cols.append("date_obs")
    
    result_df = env_df[result_cols].copy()
    
    # Ensure date_obs exists (needed for lag matrices)
    if "date_obs" not in result_df.columns or (result_df["date_obs"].isna().all() if "date_obs" in result_df.columns else True):
        if "year" in result_df.columns:
            # Create date_obs from year and doy
            logger.info(f"Creating date_obs from year and doy. Year range: {result_df['year'].min()} to {result_df['year'].max()}, DOY range: {result_df['doy'].min()} to {result_df['doy'].max()}")
            
            # Use pandas Timestamp with year and day of year
            # Convert year to int and doy to int, then use pd.Timestamp
            years = result_df["year"].astype(int)
            doys = result_df["doy"].astype(int)
            
            # Create dates using pd.Timestamp(year=year, month=1, day=1) + timedelta(days=doy-1)
            result_df["date_obs"] = pd.to_datetime(
                years.astype(str) + "-01-01"
            ) + pd.to_timedelta(doys - 1, unit="D")
            
            logger.info(f"Created date_obs: {result_df['date_obs'].notna().sum()} non-null values out of {len(result_df)}")
            logger.info(f"Date_obs range: {result_df['date_obs'].min()} to {result_df['date_obs'].max()}")
        else:
            raise EnvProcessingError(f"Cannot create date_obs: missing 'year' column. Available columns: {list(result_df.columns)}")
    
    logger.info(f"Final result_df columns: {list(result_df.columns)}, date_obs non-null: {result_df['date_obs'].notna().sum() if 'date_obs' in result_df.columns else 'N/A'}")
    
    # Calculate anomalies for both variables
    for var_name in [var1_name, var2_name]:
        # Get original values from env_df (preserves original index)
        var_values = np.array(env_df[var_name].values)
        preds = predictions[var_name]
        
        # Fill missing with predictions
        missing_mask = np.isnan(var_values)
        var_values[missing_mask] = preds[missing_mask]
        
        # Calculate anomaly: observed - predicted
        anom_values = var_values - preds
        
        # Replace NA anomalies with 0
        anom_values[np.isnan(anom_values)] = 0.0
        
        # Add to result DataFrame
        result_df[var_name] = var_values
        result_df[f"{var_name}_anom"] = anom_values
    
    logger.info(f"Weather anomalization complete: {len(result_df)} rows")
    return result_df


def create_lag_matrices(
    weather_data: pd.DataFrame,
    human_dates: pd.Series,
    arbo_ids: pd.Series,
    lag_length: int,
    var1_name: str,
    var2_name: str,
    expected_index: Optional[pd.MultiIndex] = None,
) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
    """Create lag matrices for weather variables.
    
    Args:
        weather_data: DataFrame with arbo_ID, date_obs (or doy), var1, var2, var1_anom, var2_anom
        human_dates: Series of dates to create lag matrices for
        arbo_ids: Series of arbo_IDs to create lag matrices for
        lag_length: Number of lag days
        var1_name: Name of first predictor variable
        var2_name: Name of second predictor variable
        expected_index: Optional MultiIndex to reindex pivot tables to (ensures all rows are included)
        
    Returns:
        Tuple of (lagged_data DataFrame, matrices dict with keys: var1, var2, var1_anom, var2_anom, lag, doymat)
    """
    log_step(logger, "Lag Matrix Creation", f"Lag length: {lag_length} days")
    
    # Ensure date_obs is datetime
    if "date_obs" not in weather_data.columns:
        if "doy" in weather_data.columns and "year" in weather_data.columns:
            weather_data["date_obs"] = pd.to_datetime(
                weather_data["year"].astype(str) + "-" + 
                weather_data["doy"].astype(str).str.zfill(3),
                format="%Y-%j",
                errors="coerce"
            )
        else:
            raise EnvProcessingError("weather_data must have 'date_obs' or ('doy' and 'year')")
    
    weather_data["date_obs"] = pd.to_datetime(weather_data["date_obs"])
    
    # Create lag grid
    lag_grid = []
    for arbo_id in arbo_ids.unique():
        for date_obs in human_dates:
            for lag in range(lag_length + 1):
                lag_grid.append({
                    "arbo_ID": arbo_id,
                    "date_obs": date_obs,
                    "lag": lag,
                    "date_lag": date_obs - pd.Timedelta(days=lag),
                })
    
    lag_df = pd.DataFrame(lag_grid)
    logger.info(f"Created lag grid: {len(lag_df)} rows")
    logger.info(f"Weather data shape: {weather_data.shape}, columns: {list(weather_data.columns)}")
    
    # Check ID matching
    lag_arbo_ids = set(lag_df['arbo_ID'].unique())
    weather_arbo_ids = set(weather_data['arbo_ID'].unique())
    common_ids = lag_arbo_ids & weather_arbo_ids
    logger.info(f"Lag grid arbo_IDs: {len(lag_arbo_ids)}, Weather arbo_IDs: {len(weather_arbo_ids)}, Common: {len(common_ids)}")
    if len(common_ids) == 0:
        logger.warning(f"Sample lag arbo_IDs: {list(lag_arbo_ids)[:5]}")
        logger.warning(f"Sample weather arbo_IDs: {list(weather_arbo_ids)[:5]}")
    
    # Check date matching
    lag_date_range = (lag_df['date_lag'].min(), lag_df['date_lag'].max())
    weather_date_range = (weather_data['date_obs'].min(), weather_data['date_obs'].max())
    logger.info(f"Lag date_lag range: {lag_date_range[0]} to {lag_date_range[1]}")
    logger.info(f"Weather date_obs range: {weather_date_range[0]} to {weather_date_range[1]}")
    
    # Check for overlapping dates
    lag_dates = set(lag_df['date_lag'].dt.date.unique())
    weather_dates = set(weather_data['date_obs'].dt.date.unique())
    common_dates = lag_dates & weather_dates
    logger.info(f"Lag unique dates: {len(lag_dates)}, Weather unique dates: {len(weather_dates)}, Common: {len(common_dates)}")
    
    # Join with weather data on lagged date
    lag_df = lag_df.merge(
        weather_data,
        left_on=["arbo_ID", "date_lag"],
        right_on=["arbo_ID", "date_obs"],
        how="left",
        suffixes=("", "_weather")
    )
    
    logger.info(f"After merge with weather: {len(lag_df)} rows, matched: {lag_df[var1_name].notna().sum()} rows")
    
    # Pivot to wide format: one column per lag day
    matrices = {}
    for var in [var1_name, var2_name, f"{var1_name}_anom", f"{var2_name}_anom"]:
        if var not in lag_df.columns:
            logger.warning(f"Variable {var} not found in weather data, skipping")
            continue
        
        # Create pivot table - use reindex to ensure all (arbo_ID, date_obs) combinations are included
        pivot = lag_df.pivot_table(
            index=["arbo_ID", "date_obs"],
            columns="lag",
            values=var,
            aggfunc="first"
        )
        
        logger.info(f"Pivot for {var}: {len(pivot)} rows")
        
        if len(pivot) == 0:
            raise EnvProcessingError(
                f"Pivot table for {var} is empty. This suggests no matching weather data. "
                f"Check arbo_ID and date matching between human data and weather data."
            )
        
        # Convert to numpy array (n_rows x lag_length+1)
        # Fill NaN with 0 for missing lag values
        # Note: pivot has one row per unique (arbo_ID, date_obs) combination
        # data_combined may have multiple rows per combination (e.g., different strata)
        # Alignment will be handled later in build_data_combined
        matrices[var] = pivot.fillna(0.0).values
    
    # Create lag matrix (0 to lag_length)
    n_rows = len(pivot)
    lag_matrix = np.tile(np.arange(lag_length + 1), (n_rows, 1))
    matrices["lag"] = lag_matrix
    
    # Create doymat (day of year matrix)
    if "doy" in lag_df.columns:
        doy_values = lag_df.groupby(["arbo_ID", "date_obs"])["doy"].first().values
        doymat = np.tile(doy_values.reshape(-1, 1), (1, lag_length + 1))
        matrices["doymat"] = doymat
    else:
        # Calculate doy from date_obs
        doy_values = pd.to_datetime(pivot.index.get_level_values("date_obs")).dayofyear.values
        doymat = np.tile(doy_values.reshape(-1, 1), (1, lag_length + 1))
        matrices["doymat"] = doymat
    
    logger.info(f"Lag matrices created: {n_rows} rows x {lag_length + 1} lags")
    # Return pivot index for alignment (unique (arbo_ID, date_obs) combinations)
    pivot_index = pivot.index if len(matrices) > 0 else None
    return lag_df, matrices, pivot_index


def build_data_combined(
    human_data: pd.DataFrame,
    mosquito_mir: pd.DataFrame,
    weather_data: pd.DataFrame,
    strata_data: Optional[pd.DataFrame],
    config: Dict[str, Any],
) -> pd.DataFrame:
    """Build the combined data_combined DataFrame with matrix columns.
    
    Args:
        human_data: DataFrame with arbo_ID, date_epi, year_epi, week_epi, any_cases, etc.
        mosquito_mir: DataFrame with year_epi, mir_stat (and optionally strata)
        weather_data: DataFrame with arbo_ID, date_obs, var1, var2, var1_anom, var2_anom
        strata_data: Optional strata data
        config: Configuration dict
        
    Returns:
        DataFrame with scalar columns and matrix columns (var1, var2, var1_anom, var2_anom, lag, doymat)
    """
    log_step(logger, "Building data_combined", "Assembling all components")
    
    # Start with human data frame
    data_combined = human_data.copy()
    
    # Derive year_epi and week_epi from date if needed (required for MIR merge and verification)
    if "year_epi" not in data_combined.columns or "week_epi" not in data_combined.columns:
        if "date_epi" in data_combined.columns:
            dates = pd.to_datetime(data_combined["date_epi"])
        elif "date" in data_combined.columns:
            dates = pd.to_datetime(data_combined["date"])
        else:
            raise EnvProcessingError("human_data must have 'date' or 'date_epi' to derive year_epi and week_epi")
        
        try:
            import epiweeks
            if "year_epi" not in data_combined.columns:
                data_combined["year_epi"] = dates.apply(lambda d: epiweeks.Week.fromdate(d.date()).year)
            if "week_epi" not in data_combined.columns:
                data_combined["week_epi"] = dates.apply(lambda d: epiweeks.Week.fromdate(d.date()).week)
        except ImportError:
            # Fallback: approximate using calendar year/week
            if "year_epi" not in data_combined.columns:
                data_combined["year_epi"] = dates.dt.year
            if "week_epi" not in data_combined.columns:
                # Use ISO week number as approximation (not exactly CDC epiweek, but close)
                data_combined["week_epi"] = dates.dt.isocalendar().week
                logger.warning(
                    "epiweeks package not available. Using ISO week number as week_epi approximation. "
                    "Install 'epiweeks' package for accurate CDC epiweek calculation: pip install epiweeks"
                )
    
    # Add MIR
    logger.info(f"mosquito_mir columns: {list(mosquito_mir.columns)}")
    logger.info(f"mosquito_mir shape: {mosquito_mir.shape}")
    
    merge_cols = ["year_epi"]
    if "strata" in mosquito_mir.columns:
        if strata_data is not None:
            data_combined = data_combined.merge(
                strata_data[["arbo_ID", "strata"]],
                on="arbo_ID",
                how="left"
            )
        merge_cols.append("strata")
    
    # Verify required columns exist - check each one individually
    required_cols = merge_cols + ["mir_stat"]
    available_cols = list(mosquito_mir.columns)
    
    for col in required_cols:
        if col not in available_cols:
            raise EnvProcessingError(
                f"Required column '{col}' not found in mosquito_mir. "
                f"Available columns: {available_cols}"
            )
        # Try accessing the column directly
        try:
            _ = mosquito_mir[col]
        except KeyError:
            raise EnvProcessingError(
                f"Cannot access column '{col}' from mosquito_mir despite it being in columns list. "
                f"This may indicate a column name encoding issue."
            )
    
    # Select columns for merge
    merge_df = mosquito_mir[required_cols].copy()
    logger.info(f"Merge DataFrame columns: {list(merge_df.columns)}")
    logger.info(f"data_combined columns before merge: {list(data_combined.columns)}")
    logger.info(f"merge_cols: {merge_cols}")
    
    # Verify data_combined has the merge columns
    missing_in_data_combined = [col for col in merge_cols if col not in data_combined.columns]
    if missing_in_data_combined:
        raise EnvProcessingError(
            f"data_combined missing merge columns: {missing_in_data_combined}. "
            f"Available: {list(data_combined.columns)}"
        )
    
    data_combined = data_combined.merge(
        merge_df,
        on=merge_cols,
        how="left"
    )
    
    # Create lag matrices
    var1_name = config.get("predictor_var1", "tmeanc")
    var2_name = config.get("predictor_var2", "vpd")
    lag_length = config.get("lag_length", 121)
    
    # Derive date_epi if needed (required for lag matrices)
    if "date_epi" not in data_combined.columns:
        if "date" in data_combined.columns:
            # For now, use date as date_epi (proper epiweek calculation would require epiweeks package)
            data_combined["date_epi"] = pd.to_datetime(data_combined["date"])
        else:
            raise EnvProcessingError("data_combined must have 'date' or 'date_epi' for lag matrix creation")
    
    # Create lag matrices aligned to data_combined rows
    human_dates = pd.to_datetime(data_combined["date_epi"])
    arbo_ids = data_combined["arbo_ID"]
    
    lag_df, matrices, pivot_index = create_lag_matrices(
        weather_data,
        human_dates,
        arbo_ids,
        lag_length,
        var1_name,
        var2_name,
    )
    
    # Create index for matching matrices to data_combined
    # pivot_index has unique (arbo_ID, date_obs) combinations from weather data
    # data_index has all rows from data_combined (may have duplicates from strata)
    data_index = pd.MultiIndex.from_arrays([
        data_combined["arbo_ID"],
        human_dates,
    ], names=["arbo_ID", "date_obs"])
    
    # Reorder matrices to match data_combined order
    n_rows = len(data_combined)
    lag_length_p1 = lag_length + 1
    
    # Create aligned matrices
    aligned_matrices = {}
    for matrix_name, matrix_values in matrices.items():
        if matrix_name in ["lag", "doymat"]:
            # These are created from data_combined, so they're already aligned
            if matrix_name == "lag":
                aligned_matrix = np.tile(np.arange(lag_length_p1), (n_rows, 1))
            else:  # doymat
                doy_values = pd.to_datetime(data_combined["date_epi"]).dt.dayofyear.values
                aligned_matrix = np.tile(doy_values.reshape(-1, 1), (1, lag_length_p1))
        else:
            # Weather matrices need alignment
            # matrix_values has one row per unique (arbo_ID, date_obs) from pivot
            # data_combined may have multiple rows per combination (e.g., strata)
            if pivot_index is None:
                raise EnvProcessingError("pivot_index not available for matrix alignment")
            
            if len(matrix_values) != len(pivot_index):
                raise EnvProcessingError(
                    f"Matrix {matrix_name} has {len(matrix_values)} rows, "
                    f"expected {len(pivot_index)} (from pivot index)"
                )
            
            # Create DataFrame for alignment using pivot_index
            matrix_df = pd.DataFrame(
                matrix_values,
                index=pivot_index
            )
            # Reindex to match data_combined (may have duplicates - will repeat values)
            aligned_matrix = matrix_df.reindex(data_index, method=None).values
            
            # Fill any NaN with 0 (for missing combinations)
            aligned_matrix = np.nan_to_num(aligned_matrix, nan=0.0)
        
        # Convert to list of 2D arrays (1 x lag_length+1)
        aligned_matrices[matrix_name] = [
            aligned_matrix[i:i+1, :] for i in range(n_rows)
        ]
    
    # Add matrix columns to data_combined
    # Rename variable-specific names to generic names expected by verification/modeling
    var1_name = config.get("predictor_var1", "tmeanc")
    var2_name = config.get("predictor_var2", "vpd")
    name_mapping = {
        var1_name: "var1",
        var2_name: "var2",
        f"{var1_name}_anom": "var1_anom",
        f"{var2_name}_anom": "var2_anom",
    }
    
    for matrix_name, matrix_list in aligned_matrices.items():
        # Use generic name if mapping exists, otherwise use original name
        final_name = name_mapping.get(matrix_name, matrix_name)
        data_combined[final_name] = matrix_list
    
    logger.info(f"data_combined built: {len(data_combined)} rows, {len(data_combined.columns)} columns")
    return data_combined


def process_weather(inputs: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Process weather data: compute anomalies and create lag matrices.
    
    Args:
        inputs: Dict with 'weather' key containing weather DataFrame
        config: Configuration dict
        
    Returns:
        Dict with processed weather data
    """
    log_step(logger, "Weather Processing", "Computing anomalies and lag matrices")
    
    weather_data = inputs["weather"]
    
    # Compute anomalies
    weather_anom = compute_weather_anomalies(weather_data, config)
    
    return {"weather": weather_anom}


