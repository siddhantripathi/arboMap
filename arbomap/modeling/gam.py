"""GAM fitting and predictions."""

from typing import Dict, Any

from arbomap.modeling.backend import select_backend
from arbomap.modeling.r_backend import fit_bam_models


def fit_models(
    data_combined: Any,
    model_formulas: Dict[str, str],
    config: Dict[str, Any],
) -> Any:
    """Fit the ensemble of GAMs and return per-model predictions."""
    backend = select_backend(config)
    if backend == "rpy2-mgcv":
        return fit_bam_models(data_combined, model_formulas, config)
    raise NotImplementedError("Only rpy2-mgcv backend is supported.")

