Modeling Strategy (Step 4)

Goal
Match the current R/mgcv results while enabling a long-term Python-native
implementation.

Backend Options
1) rpy2-mgcv (parity-first)
   - Use R's mgcv::bam for GAM fitting.
   - Highest likelihood of matching legacy outputs.
   - Requires local R installation and rpy2.

2) python-gam (migration path)
   - Use a Python GAM library once parity targets are met.
   - Requires careful validation of spline basis and lag-matrix handling.

Chosen Default
Use rpy2-mgcv as the default backend for parity, then migrate to python-gam
after regression tests pass.

Non-Negotiables (per rules)
- Preserve data_combined columns: var1, var2, var1_anom, var2_anom, lag, doymat, mir_stat.
- Keep ensemble aggregation identical (mean/min/max across models).
- Ensure deterministic outputs (fixed seeds, tolerances).

Implementation Notes
- The formulas in data_models/models.txt must be parsed as-is and mapped to the
  backend without altering variable names.
- Weather anomaly + lag matrix creation must happen before modeling.
- Mosquito MIR + imputation must be completed before modeling.

