if (!require("pacman")) install.packages("pacman", repos = "http://cran.us.r-project.org")
library(pacman)
pacman::p_load(readr, dplyr, lubridate, rmarkdown)

weather_files <- list.files("data_weather", pattern = "\\.csv$", full.names = TRUE)
weather_years <- weather_files %>% lapply(function(p) readr::read_csv(p, show_col_types = FALSE) %>% dplyr::select(year, doy)) %>% dplyr::bind_rows()
latest_year <- max(weather_years$year, na.rm = TRUE)
latest_doy <- max(weather_years$doy[weather_years$year == latest_year], na.rm = TRUE)
forecast_date <- as.Date(latest_doy - 1, origin = paste0(latest_year, "-01-01"))

human_data <- readr::read_csv(file.path("data_human", "simulated_human_data.csv"), show_col_types = FALSE)
human_data$date <- lubridate::mdy(human_data$date)
latest_human_year <- max(lubridate::year(human_data$date), na.rm = TRUE)

mosquito_data <- readr::read_csv(file.path("data_mosquito", "simulated_mosquito_data.csv"), show_col_types = FALSE)
mosquito_data$col_date <- lubridate::mdy(mosquito_data$col_date)
latest_mosq_year <- max(lubridate::year(mosquito_data$col_date), na.rm = TRUE)

dir.create(file.path("runs", "latest_year"), recursive = TRUE, showWarnings = FALSE)

run_params <- list(
  forecast_date = format(forecast_date, "%Y-%m-%d"),
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
  year_human_end = latest_human_year,
  year_mosquito_start = 2004,
  year_mosquito_end = latest_mosq_year,
  year_weather_start = 2001,
  year_weather_end = latest_year,
  year_compare_vis1 = 2012,
  year_compare_vis2 = latest_human_year,
  create_appendix = TRUE,
  lag_length = 121,
  case_trim_alpha = 0.02,
  dev_settings = list(
    dev_write_output = TRUE,
    model_evaluation = TRUE,
    out_folder = file.path("runs", "latest_year"),
    out_name_base = "latest_year"
  )
)

rmarkdown::render(
  "ArboMAP_forecast.Rmd",
  params = run_params,
  output_format = "html_document",
  output_file = file.path("runs", "latest_year", "latest_year_report.html")
)

