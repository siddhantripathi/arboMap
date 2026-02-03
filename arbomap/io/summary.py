"""Input summary helpers."""

from typing import Any, Dict

import pandas as pd


def summarize_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Return a serializable summary of loaded inputs."""
    summary: Dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(value, pd.DataFrame):
            summary[key] = {
                "rows": int(len(value)),
                "columns": list(value.columns),
            }
        else:
            summary[key] = {"value": value}
    return summary

