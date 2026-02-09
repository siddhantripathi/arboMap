"""Main pipeline orchestrator for ArboMAP."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from arbomap.io import load_config, load_inputs
from arbomap.ids.standardize import detect_id_type, standardize_ids
from arbomap.mosquito.mir import compute_mir, impute_mir
from arbomap.env.processing import (
    compute_weather_anomalies,
    create_lag_matrices,
    build_data_combined,
)
from arbomap.utils.logging import setup_logger, log_step, log_error_with_context


logger = setup_logger(__name__)


def run_pipeline(
    config_path: str,
    output_dir: Optional[str] = None,
    verify: bool = False,
) -> pd.DataFrame:
    """Run the complete ArboMAP pipeline.
    
    Args:
        config_path: Path to configuration YAML file
        output_dir: Optional output directory for intermediate files
        verify: If True, run verification checks (development mode)
        
    Returns:
        data_combined DataFrame ready for GAM fitting
    """
    log_step(logger, "ArboMAP Pipeline", f"Config: {config_path}")
    
    try:
        # Load configuration
        log_step(logger, "Step 1/6", "Loading configuration")
        config = load_config(config_path)
        logger.info(f"Loaded config: {config.data.get('state_name')}, {config.data.get('state_code')}")
        
        # Load inputs
        log_step(logger, "Step 2/6", "Loading and validating inputs")
        inputs = load_inputs(config.data)
        logger.info(f"Loaded inputs: {len(inputs['human'])} human, {len(inputs['mosquito'])} mosquito, "
                   f"{len(inputs['weather'])} weather rows")
        
        # Standardize IDs
        log_step(logger, "Step 3/6", "Standardizing IDs")
        # Note: spatial is a file path string, not a DataFrame, so exclude it from detect_id_type
        id_type, field_name = detect_id_type({
            "human": inputs["human"],
            "mosquito": inputs["mosquito"],
            "weather": inputs["weather"],
            "strata": inputs.get("strata"),
        })
        logger.info(f"ID type: {id_type}, field: {field_name}")
        
        # Standardize each dataset
        standardized = {
            "human": standardize_ids(inputs["human"], id_type, field_name),
            "mosquito": standardize_ids(inputs["mosquito"], id_type, field_name),
            "weather": standardize_ids(inputs["weather"], id_type, field_name),
        }
        if inputs.get("strata") is not None:
            standardized["strata"] = standardize_ids(inputs["strata"], id_type, field_name)
        # Spatial is a file path, not a DataFrame, so pass it through as-is
        if inputs.get("spatial") is not None:
            standardized["spatial"] = inputs["spatial"]
        
        # Compute MIR
        log_step(logger, "Step 4/6", "Computing mosquito MIR")
        mir_raw = compute_mir(
            standardized["mosquito"],
            standardized.get("strata"),
            config.data,
            config.data.get("year_mosquito_start", 2004),
            config.data.get("year_mosquito_end", 2018),
        )
        
        # Impute MIR
        mir_full = impute_mir(
            mir_raw,
            standardized["human"],
            standardized.get("strata"),
            config.data,
            config.data.get("year_human_start", 2004),
            config.data.get("year_human_end", 2017),
            mir_exactfit=config.data.get("dev_settings", {}).get("mir_exactfit", False),
        )
        logger.info(f"MIR computed: {len(mir_full)} year-strata combinations")
        
        # Process weather
        log_step(logger, "Step 5/6", "Processing weather data")
        weather_anom = compute_weather_anomalies(
            standardized["weather"],
            config.data,
        )
        logger.info(f"Weather anomalized: {len(weather_anom)} rows")
        
        # Build data_combined
        log_step(logger, "Step 6/6", "Building data_combined")
        data_combined = build_data_combined(
            standardized["human"],
            mir_full,
            weather_anom,
            standardized.get("strata"),
            config.data,
        )
        
        # Verification (development mode)
        if verify:
            verify_data_combined(data_combined, config.data)
        
        logger.info("Pipeline complete!")
        return data_combined
        
    except Exception as e:
        log_error_with_context(logger, e, "pipeline execution")
        raise


def verify_data_combined(data_combined: pd.DataFrame, config: Dict[str, Any]) -> None:
    """Verify data_combined structure and content (development mode).
    
    Args:
        data_combined: The data_combined DataFrame to verify
        config: Configuration dict
    """
    log_step(logger, "Verification", "Checking data_combined structure")
    
    # Check required columns
    required_scalar = ["arbo_ID", "date_epi", "year_epi", "week_epi", "mir_stat"]
    missing = [col for col in required_scalar if col not in data_combined.columns]
    if missing:
        logger.error(f"Missing required scalar columns: {missing}")
        raise ValueError(f"Missing columns: {missing}")
    
    # Check matrix columns
    required_matrices = ["var1", "var2", "var1_anom", "var2_anom", "lag", "doymat"]
    missing_matrices = [col for col in required_matrices if col not in data_combined.columns]
    if missing_matrices:
        logger.error(f"Missing required matrix columns: {missing_matrices}")
        raise ValueError(f"Missing matrix columns: {missing_matrices}")
    
    # Check matrix shapes
    lag_length = config.get("lag_length", 121)
    expected_shape = (1, lag_length + 1)
    
    for matrix_col in required_matrices:
        sample_value = data_combined[matrix_col].iloc[0]
        if isinstance(sample_value, (list, np.ndarray)):
            arr = np.asarray(sample_value)
            if arr.shape != expected_shape:
                logger.error(
                    f"Matrix column '{matrix_col}' has wrong shape: {arr.shape}, "
                    f"expected {expected_shape}"
                )
                raise ValueError(f"Matrix shape mismatch: {matrix_col}")
        else:
            logger.error(f"Matrix column '{matrix_col}' is not a matrix")
            raise ValueError(f"Invalid matrix column: {matrix_col}")
    
    # Check row counts
    n_rows = len(data_combined)
    logger.info(f"Verification passed: {n_rows} rows, {len(data_combined.columns)} columns")
    logger.info(f"  Scalar columns: {len([c for c in data_combined.columns if c not in required_matrices])}")
    logger.info(f"  Matrix columns: {len(required_matrices)}")
    
    # Check for missing values in critical columns
    critical_cols = ["arbo_ID", "mir_stat", "any_cases"]
    for col in critical_cols:
        if col in data_combined.columns:
            n_missing = data_combined[col].isna().sum()
            if n_missing > 0:
                logger.warning(f"Column '{col}' has {n_missing} missing values")
    
    logger.info("Verification complete - all checks passed")
