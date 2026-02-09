"""ID standardization utilities."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import pandas as pd

FIPS_FIELDS = ("fips", "FIPS", "fips_code", "FIPS_CODE")
NAME_FIELDS = ("county", "district", "parish", "Parish")


class IdError(RuntimeError):
    """Raised when ID validation or standardization fails."""


def detect_id_type(datasets: Dict[str, Optional[pd.DataFrame]]) -> Tuple[str, str]:
    """Detect and validate a single ID type across datasets.

    Returns (id_type, field_name). id_type is "fips" or "name".
    Prefers name IDs if all datasets provide them; otherwise FIPS if all provide
    FIPS; otherwise raises.
    """
    available = {}
    for name, df in datasets.items():
        if df is None:
            continue
        fields = set(df.columns)
        has_fips = any(field in fields for field in FIPS_FIELDS)
        has_name = any(field in fields for field in NAME_FIELDS)
        if not has_fips and not has_name:
            raise IdError(f"{name} has no accepted ID field.")
        available[name] = {"fips": has_fips, "name": has_name}

    if all(flags["name"] for flags in available.values()):
        id_type = "name"
    elif all(flags["fips"] for flags in available.values()):
        id_type = "fips"
    else:
        raise IdError(
            "ID types are mixed across datasets. Use FIPS or name consistently."
        )

    field_name = _first_matching_field(
        datasets, FIPS_FIELDS if id_type == "fips" else NAME_FIELDS
    )
    return id_type, field_name


def standardize_ids(df: pd.DataFrame, id_type: str, field_name: str) -> pd.DataFrame:
    """Create arbo_ID with strict FIPS or name-based matching (never mixed)."""
    if field_name not in df.columns:
        raise IdError(f"ID field {field_name} not found in dataset.")

    df = df.copy()
    if id_type == "fips":
        df["arbo_ID"] = _normalize_fips(df[field_name])
    elif id_type == "name":
        # Normalize names: strip whitespace and convert to lowercase
        # This matches the original R code's simplifynames() function which uses tolower()
        df["arbo_ID"] = df[field_name].astype(str).str.strip().str.lower()
    else:
        raise IdError(f"Unknown id_type: {id_type}")

    return df


def _first_matching_field(
    datasets: Dict[str, Optional[pd.DataFrame]],
    fields: Tuple[str, ...],
) -> str:
    for df in datasets.values():
        if df is None:
            continue
        for field in fields:
            if field in df.columns:
                return field
    raise IdError("No matching ID field found in datasets.")


def _normalize_fips(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip()
    # Pad to 5 when possible; reject <4 chars to avoid ambiguous FIPS.
    length = values.str.len()
    values = values.where(length != 4, values.str.zfill(5))
    if (length < 4).any():
        raise IdError(
            "FIPS values must be 4 or 5 characters (state prefix required)."
        )
    return values

