ArboMAP Python Scaffold

This package is a modular scaffold for the ArboMAP rewrite.
Modules align with required boundaries:

- io: data loading and schema validation
- ids: ID standardization (FIPS vs name gate)
- mosquito: MIR modeling + imputation (single module boundary)
- env: weather anomalies + lag matrices (single module boundary)
- modeling: GAM fitting + ensemble aggregation
- report: HTML/PDF rendering from serialized outputs
- app: desktop UI and orchestration

Do not rename data_combined fields used in model formulas:
var1, var2, var1_anom, var2_anom, lag, doymat, mir_stat

