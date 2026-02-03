"""Pipeline orchestration boundaries for ArboMAP."""

from dataclasses import dataclass
from typing import Dict, Any

from arbomap.ids.standardize import detect_id_type, standardize_ids
from arbomap.io.loader import load_inputs, validate_inputs
from arbomap.io.summary import summarize_inputs


@dataclass
class RunConfig:
    """Run configuration loaded from config/default_config.yaml."""

    params: Dict[str, Any]


def run_pipeline(config: RunConfig) -> Dict[str, Any]:
    """Execute the modular pipeline and return serializable outputs."""
    inputs = load_inputs(config.params)
    validate_inputs(inputs, config.params)

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

    # TODO: call mosquito, env, modeling, and report modules
    return {
        "inputs": inputs,
        "id_type": id_type,
        "summary": summarize_inputs(inputs),
    }

