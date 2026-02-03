Baseline Capture (Step 1)

Purpose
Run the existing R workflow to produce canonical outputs that will be used
for parity checks in the Python rewrite.

How to run
1) Open `ArboMAP.Rproj` in RStudio.
2) Run `baseline/run_baseline.R`.
3) Verify outputs appear in `baseline/outputs`.

What this does
- Renders `ArboMAP_forecast.Rmd` with explicit params.
- Enables dev outputs and model evaluations.
- Writes all outputs into `baseline/outputs` using a consistent name prefix.

Notes
- Do not modify formulas or data during baseline capture.
- Keep the output files as the reference for regression tests.

