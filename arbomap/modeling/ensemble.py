"""Ensemble aggregation logic (mean/min/max across models)."""

from typing import Any


def aggregate_predictions(preds: Any) -> Any:
    """Compute model mean/min/max aggregates for reporting."""
    raise NotImplementedError("Ensemble aggregation is not implemented yet.")

