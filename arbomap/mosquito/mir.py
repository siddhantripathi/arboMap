"""Mosquito infection modeling and MIR imputation using R/lme4 via rpy2."""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from arbomap.utils.logging import setup_logger, log_step, log_error_with_context


logger = setup_logger(__name__)


class MirError(RuntimeError):
    """Raised when MIR calculation fails."""


def compute_mir(
    mosquito_data: pd.DataFrame,
    strata_data: Optional[pd.DataFrame],
    config: Dict[str, Any],
    year_start: int,
    year_end: int,
) -> pd.DataFrame:
    """Compute MIR statistics using R/lme4 via rpy2.
    
    Args:
        mosquito_data: DataFrame with columns: arbo_ID, year_epi, doy, wnv_result
        strata_data: Optional DataFrame with columns: arbo_ID, strata (for stratified models)
        config: Configuration dict with 'mosquito_model' key
        year_start: Start year for modeling period
        year_end: End year for modeling period
        
    Returns:
        DataFrame with columns: year_epi, mir_stat_raw (and optionally strata)
    """
    log_step(logger, "MIR Calculation", f"Model: {config.get('mosquito_model', 'MIGR')}")
    
    try:
        import rpy2.robjects as robjects
        from rpy2.robjects import pandas2ri
        from rpy2.robjects import conversion
        from rpy2.robjects.packages import importr
    except ImportError as exc:
        raise MirError("rpy2 and R packages (lme4, nlme) are required for MIR calculation.") from exc
    
    try:
        lme4 = importr("lme4")
        nlme = importr("nlme")
    except Exception as exc:
        raise MirError("R packages 'lme4' and 'nlme' must be installed.") from exc
    
    mosquito_model = config.get("mosquito_model", "MIGR")
    mosq_nonstrat = ["simpleratio", "AUC", "MIGR", "MII"]
    mosq_strat = ["stratifiedMIGR", "stratifiedMII"]
    
    # Normalize model name
    if mosquito_model in mosq_nonstrat + mosq_strat:
        model_clean = mosquito_model
    else:
        logger.warning(f"Unknown mosquito model '{mosquito_model}', defaulting to 'MIGR'")
        model_clean = "MIGR"
    
    # Prepare mosquito data for R
    mosq_r = mosquito_data.copy()
    
    # Derive date_obs from date column if needed
    if "date_obs" not in mosq_r.columns and "date" in mosq_r.columns:
        mosq_r["date_obs"] = pd.to_datetime(mosq_r["date"])
    
    # Derive year_epi from date_obs (epiyear - CDC epiweeks)
    if "year_epi" not in mosq_r.columns:
        if "date_obs" not in mosq_r.columns:
            raise MirError("mosquito_data must have 'date' or 'date_obs' column to derive year_epi")
        # Calculate epiyear: year of the date, but if date is in first few days of year
        # and epiweek is 52/53, it belongs to previous epiyear
        dates = pd.to_datetime(mosq_r["date_obs"])
        # Use epiweeks package if available, otherwise approximate
        try:
            import epiweeks
            mosq_r["year_epi"] = dates.apply(lambda d: epiweeks.Week.fromdate(d.date()).year)
            logger.debug("Using epiweeks package for year_epi calculation")
        except ImportError:
            # Fallback: use calendar year (epiyear is usually same as calendar year)
            # For dates in early Jan that belong to previous epiyear (epiweek 52/53),
            # this will be slightly wrong, but acceptable for most cases
            mosq_r["year_epi"] = dates.dt.year
            logger.warning(
                "epiweeks package not available. Using calendar year as year_epi. "
                "Install 'epiweeks' package for accurate epiyear calculation: pip install epiweeks"
            )
    
    # Derive doy if missing
    if "doy" not in mosq_r.columns:
        if "date_obs" not in mosq_r.columns:
            raise MirError("mosquito_data must have 'date' or 'date_obs' column to derive doy")
        mosq_r["doy"] = pd.to_datetime(mosq_r["date_obs"]).dt.dayofyear
    
    # Calculate dminus (centered DOY) in Python before converting to R
    doy_mean = float(mosq_r["doy"].mean())
    mosq_r["dminus"] = mosq_r["doy"] - doy_mean
    
    # Ensure required columns exist
    required_cols = ["arbo_ID", "year_epi", "doy", "dminus", "wnv_result"]
    missing_cols = [col for col in required_cols if col not in mosq_r.columns]
    if missing_cols:
        raise MirError(f"mosquito_data missing required columns: {missing_cols}")
    
    # Convert to R data frame with all needed columns including dminus
    with conversion.localconverter(pandas2ri.converter):
        r_mosq = conversion.py2rpy(mosq_r[required_cols].copy())
    
    # Convert year_epi to factor in R using R code execution (most reliable method)
    # Assign data frame to R variable, modify it, then get it back
    robjects.r.assign("temp_mosq", r_mosq)
    robjects.r("temp_mosq$year_epi <- factor(temp_mosq$year_epi)")
    r_mosq = robjects.r["temp_mosq"]
    
    mir_result = None
    
    # simpleratio model
    if model_clean == "simpleratio":
        logger.info("Computing simpleratio MIR")
        r_result = robjects.r("""
        function(df) {
          df %>% 
            dplyr::group_by(year_epi) %>% 
            dplyr::summarise(
              tot_pos = sum(wnv_result, na.rm=TRUE),
              tot_test = n(),
              .groups = "drop"
            ) %>%
            dplyr::mutate(mir_stat_raw = tot_pos / tot_test) %>%
            dplyr::select(year_epi, mir_stat_raw) %>%
            dplyr::mutate(year_epi = as.numeric(as.character(year_epi)))
        }
        """)(r_mosq)
        
        with conversion.localconverter(pandas2ri.converter):
            mir_result = conversion.rpy2py(r_result)
    
    # AUC, MIGR, MII models (non-stratified)
    elif model_clean in ["AUC", "MIGR", "MII"]:
        logger.info(f"Computing {model_clean} MIR using lme4::glmer")
        
        if model_clean == "AUC":
            formula_str = "wnv_result ~ poly(dminus, 2) + (poly(dminus, 2)|year_epi)"
        else:  # MIGR or MII
            formula_str = "wnv_result ~ 1 + dminus + (0+1|year_epi) + (0+dminus|year_epi)"
        
        r_formula = robjects.Formula(formula_str)
        mir_glm = lme4.glmer(
            r_formula,
            family=robjects.r["binomial"](),
            data=r_mosq,
        )
        
        # Extract random effects
        re = nlme.random_effects(mir_glm)
        year_re = re.rx2("year_epi")
        
        if model_clean == "AUC":
            # AUC: sum predictions across dminus range
            logger.warning("AUC model requires prediction grid - using simplified approach")
            # For now, use intercept from MIGR as approximation
            mir_stat_raw = np.array(year_re.rx(True, 1))  # First column (intercept)
        elif model_clean == "MIGR":
            mir_stat_raw = np.array(year_re.rx(True, 1))  # First column (intercept)
        else:  # MII
            mir_stat_raw = np.array(year_re.rx(True, 2))  # Second column (dminus)
        
        year_levels = list(year_re.rownames)
        mir_result = pd.DataFrame({
            "year_epi": [int(y) for y in year_levels],
            "mir_stat_raw": mir_stat_raw.flatten(),
        })
    
    # Stratified models
    elif model_clean in mosq_strat:
        if strata_data is None:
            raise MirError(f"Stratified model '{model_clean}' requires strata_data")
        
        logger.info(f"Computing {model_clean} MIR with strata using lme4::glmer")
        
        # Debug: Check ID matching
        mosq_ids = set(mosq_r["arbo_ID"].unique())
        strata_ids = set(strata_data["arbo_ID"].unique())
        logger.info(f"Mosquito data has {len(mosq_ids)} unique arbo_IDs, strata has {len(strata_ids)} unique arbo_IDs")
        common_ids = mosq_ids & strata_ids
        logger.info(f"Common IDs: {len(common_ids)}")
        if len(common_ids) == 0:
            logger.warning(f"Sample mosquito IDs: {list(mosq_ids)[:5]}")
            logger.warning(f"Sample strata IDs: {list(strata_ids)[:5]}")
        
        # Join strata to mosquito data
        mosq_with_strata = mosq_r.merge(
            strata_data[["arbo_ID", "strata"]],
            on="arbo_ID",
            how="inner"
        ).dropna(subset=["strata"])
        
        logger.info(f"After merge with strata: {len(mosq_with_strata)} rows")
        
        if len(mosq_with_strata) == 0:
            raise MirError(
                f"No rows after merging mosquito data with strata. "
                f"Mosquito has {len(mosq_ids)} unique IDs, strata has {len(strata_ids)} unique IDs, "
                f"common: {len(common_ids)}. Check arbo_ID matching."
            )
        
        # Calculate dminus for stratified data (centered DOY)
        doy_mean_strat = float(mosq_with_strata["doy"].mean())
        mosq_with_strata["dminus"] = mosq_with_strata["doy"] - doy_mean_strat
        
        # Create stratum_year in Python before converting to R
        # Ensure both components are strings
        mosq_with_strata["stratum_year"] = (
            mosq_with_strata["strata"].astype(str) + "_" + 
            mosq_with_strata["year_epi"].astype(str)
        )
        
        # Convert to categorical BEFORE R conversion (will become R factor automatically)
        # This matches the original R code: stratum_year = paste(strata, year_epi, sep = "_") %>% factor()
        mosq_with_strata["stratum_year"] = pd.Categorical(mosq_with_strata["stratum_year"])
        
        # Convert to R data frame - stratum_year will automatically be an R factor
        with conversion.localconverter(pandas2ri.converter):
            r_mosq_strat = conversion.py2rpy(
                mosq_with_strata[["arbo_ID", "year_epi", "doy", "dminus", "wnv_result", "strata", "stratum_year"]].copy()
            )
        
        # Ensure it's a proper data frame (matching original R code: as.data.frame())
        # Use the R object directly instead of assigning to avoid data loss
        r_mosq_strat = robjects.r["as.data.frame"](r_mosq_strat)
        
        # Verify the data frame structure
        logger.info(f"R data frame has {len(r_mosq_strat)} rows, columns: {list(r_mosq_strat.names)}")
        
        # Verify factor type and levels
        stratum_year_type = robjects.r["class"](r_mosq_strat.rx2("stratum_year"))[0]
        n_levels = int(robjects.r["length"](robjects.r["levels"](r_mosq_strat.rx2("stratum_year")))[0])
        logger.info(f"stratum_year type: {stratum_year_type}, levels: {n_levels}")
        
        if stratum_year_type != "factor":
            raise MirError(f"stratum_year is not a factor (type: {stratum_year_type})")
        if n_levels == 0:
            raise MirError("stratum_year factor has no levels - cannot use in glmer")
        
        formula_str = "wnv_result ~ 1 + dminus + (0+1|stratum_year) + (0+dminus|stratum_year)"
        r_formula = robjects.Formula(formula_str)
        
        # Try calling glmer with explicit data frame reference
        logger.info("Calling glmer...")
        mir_glm = lme4.glmer(
            r_formula,
            family=robjects.r["binomial"](),
            data=r_mosq_strat,
        )
        
        # Extract random effects
        re = nlme.random_effects(mir_glm)
        stratum_re = re.rx2("stratum_year")
        
        if model_clean == "stratifiedMIGR":
            mir_stat_raw = np.array(stratum_re.rx(True, 1))  # First column
        else:  # stratifiedMII
            mir_stat_raw = np.array(stratum_re.rx(True, 2))  # Second column
        
        stratum_levels = list(stratum_re.rownames)
        # Parse stratum_year back to strata and year_epi
        parsed = [s.split("_") for s in stratum_levels]
        mir_result = pd.DataFrame({
            "strata": [p[0] for p in parsed],
            "year_epi": [int(p[1]) for p in parsed],
            "mir_stat_raw": mir_stat_raw.flatten(),
        })
        # Convert strata back to original type
        if strata_data is not None and len(strata_data) > 0:
            strata_type = type(strata_data["strata"].iloc[0])
            mir_result["strata"] = mir_result["strata"].astype(strata_type)
    
    else:
        raise MirError(f"Unsupported mosquito model: {model_clean}")
    
    logger.info(f"MIR calculation complete: {len(mir_result)} rows")
    return mir_result


def impute_mir(
    mir_raw: pd.DataFrame,
    human_data: pd.DataFrame,
    strata_data: Optional[pd.DataFrame],
    config: Dict[str, Any],
    year_start: int,
    year_end: int,
    mir_exactfit: bool = False,
) -> pd.DataFrame:
    """Impute missing MIR values and center the statistic.
    
    Args:
        mir_raw: DataFrame with mir_stat_raw (and optionally strata)
        human_data: DataFrame with year_epi and arbo_ID columns
        strata_data: Optional strata data for stratified models
        config: Configuration dict
        year_start: Start year for modeling
        year_end: End year for modeling
        mir_exactfit: If True, use exactfit method (impute as 0), else use MIR-human model
        
    Returns:
        DataFrame with mir_stat (final imputed and centered statistic)
    """
    log_step(logger, "MIR Imputation", f"Method: {'exactfit' if mir_exactfit else 'MIR-human model'}")
    
    mosquito_model = config.get("mosquito_model", "MIGR")
    mosq_nonstrat = ["simpleratio", "AUC", "MIGR", "MII"]
    mosq_strat = ["stratifiedMIGR", "stratifiedMII"]
    
    if mosquito_model in mosq_nonstrat:
        is_stratified = False
    elif mosquito_model in mosq_strat:
        is_stratified = True
    else:
        is_stratified = False
    
    # Create full grid of years (and optionally strata)
    if is_stratified:
        if strata_data is None:
            raise MirError("Stratified model requires strata_data for imputation")
        strata_values = sorted(strata_data["strata"].unique())
        mir_full = pd.MultiIndex.from_product(
            [strata_values, range(year_start, year_end + 1)],
            names=["strata", "year_epi"]
        ).to_frame(index=False)
    else:
        mir_full = pd.DataFrame({"year_epi": range(year_start, year_end + 1)})
    
    # Join with known MIR values
    mir_full = mir_full.merge(mir_raw, on=["year_epi"] + (["strata"] if is_stratified else []), how="left")
    mir_full["mir_imputed"] = mir_full["mir_stat_raw"].isna()
    
    if mir_exactfit:
        # Center and impute missing as 0
        mir_mean = mir_full["mir_stat_raw"].mean()
        mir_full["mir_stat_ctr"] = mir_full["mir_stat_raw"] - mir_mean
        mir_full["mir_stat"] = mir_full["mir_stat_ctr"].fillna(0.0)
        logger.info("Using exactfit: missing MIR imputed as 0 (average risk)")
    else:
        # MIR-human model: predict missing MIR from human cases
        # Ensure human_data has year_epi (derive from date if needed)
        human_work = human_data.copy()
        if "year_epi" not in human_work.columns:
            if "date_obs" in human_work.columns:
                dates = pd.to_datetime(human_work["date_obs"])
                try:
                    import epiweeks
                    human_work["year_epi"] = dates.apply(lambda d: epiweeks.Week.fromdate(d.date()).year)
                except ImportError:
                    human_work["year_epi"] = dates.dt.year
            elif "date" in human_work.columns:
                dates = pd.to_datetime(human_work["date"])
                try:
                    import epiweeks
                    human_work["year_epi"] = dates.apply(lambda d: epiweeks.Week.fromdate(d.date()).year)
                except ImportError:
                    human_work["year_epi"] = dates.dt.year
            else:
                raise MirError("human_data must have 'date' or 'date_obs' column to derive year_epi")
        
        if is_stratified:
            human_total = human_work.merge(
                strata_data[["arbo_ID", "strata"]],
                on="arbo_ID",
                how="left"
            ).groupby(["year_epi", "strata"]).size().reset_index(name="tot_cases")
        else:
            human_total = human_work.groupby("year_epi").size().reset_index(name="tot_cases")
        
        mir_full = mir_full.merge(human_total, on=["year_epi"] + (["strata"] if is_stratified else []), how="left")
        
        # Fit linear model
        train_data = mir_full.dropna(subset=["mir_stat_raw", "tot_cases"])
        if len(train_data) == 0:
            logger.warning("No training data for MIR-human model, using exactfit fallback")
            mir_mean = mir_full["mir_stat_raw"].mean()
            mir_full["mir_stat_ctr"] = mir_full["mir_stat_raw"] - mir_mean
            mir_full["mir_stat"] = mir_full["mir_stat_ctr"].fillna(0.0)
        else:
            if is_stratified:
                # Stratified: mir_stat_raw ~ tot_cases * strata
                from sklearn.linear_model import LinearRegression
                # One-hot encode strata
                train_X = pd.get_dummies(train_data[["tot_cases", "strata"]], columns=["strata"])
                model = LinearRegression()
                model.fit(train_X, train_data["mir_stat_raw"])
                
                # Predict for all rows
                pred_X = pd.get_dummies(mir_full[["tot_cases", "strata"]], columns=["strata"])
                # Align columns
                pred_X = pred_X.reindex(columns=train_X.columns, fill_value=0)
                mir_full["pred"] = model.predict(pred_X)
            else:
                # Non-stratified: mir_stat_raw ~ tot_cases
                from sklearn.linear_model import LinearRegression
                model = LinearRegression()
                model.fit(train_data[["tot_cases"]], train_data["mir_stat_raw"])
                mir_full["pred"] = model.predict(mir_full[["tot_cases"]])
            
            # Impute missing values
            mir_full["mir_stat_imp"] = mir_full["mir_stat_raw"].fillna(mir_full["pred"])
            # Center
            mir_mean = mir_full["mir_stat_imp"].mean()
            mir_full["mir_stat_ctr"] = mir_full["mir_stat_imp"] - mir_mean
            # If still missing (no human cases for forecast year), use 0
            mir_full["mir_stat"] = mir_full["mir_stat_ctr"].fillna(0.0)
            logger.info(f"MIR-human model: imputed {mir_full['mir_imputed'].sum()} missing values")
    
    logger.info(f"MIR imputation complete: {len(mir_full)} rows, mean={mir_full['mir_stat'].mean():.6f}")
    return mir_full
