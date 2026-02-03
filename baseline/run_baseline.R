if (!require("pacman")) install.packages("pacman", repos = "http://cran.us.r-project.org")
library(pacman)
pacman::p_load(rmarkdown)

# Baseline parameters aligned to the default Rmd values.
baseline_params <- list(
  forecast_date = "2018-08-15",
  state_name = "South Dakota",
  state_code = "SD",
  predictor_var1 = "tmeanc",
  predictor_var2 = "vpd",
  mosquito_model = "stratifiedMIGR",
  mosquito_doy_start = 140,
  mosquito_doy_end = 366,
  file_human = file.path("data_human", "simulated_human_data.csv"),
  file_mosquito = file.path("data_mosquito", "simulated_mosquito_data.csv"),
  file_strata = file.path("data_strata", "example_strata_SD.csv"),
  file_county_sf = file.path("data_spatial", "sd_counties.RDS"),
  file_models = file.path("data_models", "models.txt"),
  folder_weather = "data_weather",
  year_human_start = 2004,
  year_human_end = 2017,
  year_mosquito_start = 2004,
  year_mosquito_end = 2018,
  year_weather_start = 2000,
  year_weather_end = 2018,
  year_compare_vis1 = 2012,
  year_compare_vis2 = 2017,
  create_appendix = TRUE,
  lag_length = 121,
  case_trim_alpha = 0.02,
  dev_settings = list(
    dev_write_output = TRUE,
    model_evaluation = TRUE,
    out_folder = file.path("baseline", "outputs"),
    out_name_base = "baseline_run"
  )
)

rmarkdown::render(
  "ArboMAP_forecast.Rmd",
  params = baseline_params,
  output_format = "html_document",
  output_file = file.path("baseline", "outputs", "baseline_run_report.html")
)

