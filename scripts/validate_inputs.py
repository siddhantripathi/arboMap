"""Validate inputs against config and print a summary."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arbomap.io import load_config, load_inputs, validate_inputs, summarize_inputs
from arbomap.ids.standardize import detect_id_type


def main() -> None:
    config = load_config("config/default_config.yaml")
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

    summary = summarize_inputs(inputs)
    print(f"ID type: {id_type} ({field_name})")
    for key, value in summary.items():
        if "rows" in value:
            print(f"{key}: {value['rows']} rows, {len(value['columns'])} columns")
        else:
            print(f"{key}: {value['value']}")


if __name__ == "__main__":
    main()

