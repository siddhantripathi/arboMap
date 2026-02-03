"""Data loading and schema validation."""

from __future__ import annotations

from typing import Dict, Any, List

import os
import pandas as pd

from arbomap.ids.standardize import detect_id_type


class InputError(RuntimeError):
    """Raised when inputs are missing or invalid."""


def load_inputs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Load human, mosquito, weather, strata, spatial, and model formula data."""
    inputs: Dict[str, Any] = {}

    _ensure_exists(config["file_human"])
    inputs["human"] = pd.read_csv(config["file_human"])
    _ensure_exists(config["file_mosquito"])
    inputs["mosquito"] = _load_mosquito(config["file_mosquito"])

    strata_path = config.get("file_strata", "")
    inputs["strata"] = pd.read_csv(strata_path) if strata_path else None

    _ensure_exists(config["file_models"])
    inputs["models"] = _load_models(config["file_models"])
    _ensure_folder_exists(config["folder_weather"])
    inputs["weather"] = _load_weather_folder(config["folder_weather"])

    spatial_path = config.get("file_county_sf")
    if spatial_path:
        _ensure_exists(spatial_path)
    inputs["spatial"] = spatial_path
    return inputs


def validate_inputs(inputs: Dict[str, Any], config: Dict[str, Any]) -> None:
    """Validate input schemas and enforce ID-type gate (FIPS vs name)."""
    _ensure_mosquito_doy(inputs["mosquito"])
    _require_columns(inputs["human"], ["date"])
    _require_columns(inputs["mosquito"], ["date", "wnv_result", "doy"])
    _require_columns(inputs["weather"], ["year", "doy"])
    _require_columns(inputs["weather"], [config["predictor_var1"], config["predictor_var2"]])

    if inputs.get("strata") is not None:
        _require_columns(inputs["strata"], ["strata"])

    if inputs.get("models") is None or len(inputs["models"]) == 0:
        raise InputError("No model formulas loaded.")

    # Enforce ID-type gate (FIPS vs name) across datasets.
    detect_id_type(
        {
            "human": inputs["human"],
            "mosquito": inputs["mosquito"],
            "weather": inputs["weather"],
            "strata": inputs.get("strata"),
        }
    )


def _require_columns(df: pd.DataFrame, columns: List[str]) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise InputError(f"Missing required columns: {missing}")


def _load_models(path: str) -> Dict[str, str]:
    models = pd.read_csv(path, header=None, quotechar="\"", dtype=str)
    if models.shape[1] < 2:
        raise InputError("Model formulas file must contain name and formula.")
    return dict(zip(models.iloc[:, 0], models.iloc[:, 1]))


def _load_mosquito(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns and "col_date" in df.columns:
        df = df.rename(columns={"col_date": "date"})
    _ensure_mosquito_doy(df)
    return df


def _ensure_mosquito_doy(df: pd.DataFrame) -> None:
    if "date" in df.columns and "doy" not in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce")
        if dates.isna().any():
            raise InputError("Mosquito date parsing failed; invalid date values.")
        df["doy"] = dates.dt.dayofyear


def _load_weather_folder(folder: str) -> pd.DataFrame:
    csv_files = sorted(
        [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if name.lower().endswith(".csv")
        ]
    )
    if not csv_files:
        raise InputError("No weather CSV files found.")

    frames = []
    for path in csv_files:
        frame = pd.read_csv(path)
        frame["file_time"] = os.path.getmtime(path)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _ensure_exists(path: str) -> None:
    if not os.path.exists(path):
        raise InputError(f"File not found: {path}")


def _ensure_folder_exists(path: str) -> None:
    if not os.path.isdir(path):
        raise InputError(f"Folder not found: {path}")

