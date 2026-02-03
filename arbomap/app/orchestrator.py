"""Pipeline orchestration for the desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from arbomap.io import load_config, load_inputs, validate_inputs, summarize_inputs
from arbomap.ids.standardize import detect_id_type, standardize_ids


@dataclass
class OrchestrationResult:
    inputs: Dict[str, Any]
    id_type: str
    summary: Dict[str, Any]


def run_local(config_path: str) -> OrchestrationResult:
    """Run the pipeline locally for the desktop app."""
    config = load_config(config_path)
    inputs = load_inputs(config.data)
    validate_inputs(inputs, config.data)

    id_type, field_name = detect_id_type(
        {
            "human": inputs["human"],
            "mosquito": inputs["mosquito"],
            "weather": inputs["weather"],
            "strata": inputs.get("strata"),
        }
    )

    inputs["human"] = standardize_ids(inputs["human"], id_type, field_name)
    inputs["mosquito"] = standardize_ids(inputs["mosquito"], id_type, field_name)
    inputs["weather"] = standardize_ids(inputs["weather"], id_type, field_name)
    if inputs.get("strata") is not None:
        inputs["strata"] = standardize_ids(inputs["strata"], id_type, field_name)

    summary = summarize_inputs(inputs)
    return OrchestrationResult(inputs=inputs, id_type=id_type, summary=summary)

