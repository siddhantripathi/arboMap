if (!require("pacman")) install.packages("pacman", repos = "http://cran.us.r-project.org")
library(pacman)
pacman::p_load(yaml, rmarkdown, readr, dplyr, lubridate)

args <- commandArgs(trailingOnly = TRUE)
config_path <- ifelse(length(args) >= 1, args[[1]], "config/default_config.yaml")
out_dir <- ifelse(length(args) >= 2, args[[2]], file.path("runs", "data_combined"))

cfg <- yaml::read_yaml(config_path)

weather_files <- list.files(cfg$folder_weather, pattern = "\\.csv$", full.names = TRUE)
weather_years <- weather_files %>%
  lapply(function(p) readr::read_csv(p, show_col_types = FALSE) %>% dplyr::select(year, doy)) %>%
  dplyr::bind_rows()
latest_year <- max(weather_years$year, na.rm = TRUE)
latest_doy <- max(weather_years$doy[weather_years$year == latest_year], na.rm = TRUE)
forecast_date <- as.Date(latest_doy - 1, origin = paste0(latest_year, "-01-01"))

human_data <- readr::read_csv(cfg$file_human, show_col_types = FALSE)
human_data$date <- lubridate::mdy(human_data$date)
latest_human_year <- max(lubridate::year(human_data$date), na.rm = TRUE)

mosquito_data <- readr::read_csv(cfg$file_mosquito, show_col_types = FALSE)
mosquito_data$col_date <- lubridate::mdy(mosquito_data$col_date)
latest_mosq_year <- max(lubridate::year(mosquito_data$col_date), na.rm = TRUE)

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

run_params <- list(
  forecast_date = format(forecast_date, "%Y-%m-%d"),
  state_name = cfg$state_name,
  state_code = cfg$state_code,
  predictor_var1 = cfg$predictor_var1,
  predictor_var2 = cfg$predictor_var2,
  mosquito_model = cfg$mosquito_model,
  mosquito_doy_start = cfg$mosquito_doy_start,
  mosquito_doy_end = cfg$mosquito_doy_end,
  file_human = cfg$file_human,
  file_mosquito = cfg$file_mosquito,
  file_strata = cfg$file_strata,
  file_county_sf = cfg$file_county_sf,
  file_models = cfg$file_models,
  folder_weather = cfg$folder_weather,
  year_human_start = cfg$year_human_start,
  year_human_end = latest_human_year,
  year_mosquito_start = cfg$year_mosquito_start,
  year_mosquito_end = latest_mosq_year,
  year_weather_start = cfg$year_weather_start,
  year_weather_end = latest_year,
  year_compare_vis1 = cfg$year_compare_vis1,
  year_compare_vis2 = latest_human_year,
  create_appendix = FALSE,
  lag_length = cfg$lag_length,
  case_trim_alpha = cfg$case_trim_alpha,
  dev_settings = list(
    dev_write_output = TRUE,
    model_evaluation = FALSE,
    out_folder = out_dir,
    out_name_base = "data_combined_build"
  )
)

rmarkdown::render(
  "ArboMAP_forecast.Rmd",
  params = run_params,
  output_format = "html_document",
  output_file = file.path(out_dir, "data_combined_build_report.html")
)

