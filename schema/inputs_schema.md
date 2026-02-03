Input Schema Contracts

Overview
ArboMAP expects consistent identifiers across human, mosquito, and weather data.
IDs must be either FIPS or names, never mixed. Spatial data must align with the
chosen ID type. Dates are standardized to CDC/MMWR epiweeks.

Accepted ID field names
- FIPS: fips, FIPS, fips_code, FIPS_CODE
- Names: county, district, parish, Parish

Human case data (CSV)
Required columns:
- date: case onset date (parsed to epiweek)
- county ID: one of the accepted ID fields
Notes:
- Do not include the forecast year in human data (reporting lag issue).
- Records are individual cases; weekly counts are derived internally.

Mosquito pool data (CSV)
Required columns:
- date: pool collection date
- wnv_result: 0/1 (negative/positive)
- doy: day of year (1-366)
- county ID: one of the accepted ID fields
Optional / used if provided:
- year (year of observation)
Notes:
- Stratified models require a strata join via the strata file.

Strata data (CSV, optional)
Required columns:
- county ID: one of the accepted ID fields
- strata: stratum identifier (numeric or string)

Weather/environment data (CSV)
Required columns:
- year: numeric year
- doy: day of year (1-366)
- predictor_var1 (default tmeanc)
- predictor_var2 (default vpd)
- county ID: one of the accepted ID fields
Notes:
- Weather data are deduplicated by "latest value per day" logic.
- Anomalies are computed internally; do not pre-anomalize inputs.

Spatial data (RDS or shapefile)
Required:
- US county boundaries for the target state
Notes:
- IDs are matched internally against the chosen ID type.

Model formulas (CSV)
Location: data_models/models.txt
Format: "model_name","formula"
Notes:
- Formulas directly reference data_combined fields:
  var1, var2, var1_anom, var2_anom, lag, doymat, mir_stat, arbo_ID, doy.

ID Type Gate
All of human, mosquito, weather (and strata if used) must share the same ID type.
If any dataset is missing the accepted field for the chosen ID type, the run
must fail with a clear error.

