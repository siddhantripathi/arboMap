"""Modeling backend selection."""

from typing import Dict, Any


class BackendError(RuntimeError):
    """Raised when an unsupported modeling backend is requested."""


def select_backend(config: Dict[str, Any]) -> str:
    backend = config.get("modeling", {}).get("backend", "rpy2-mgcv")
    if backend != "rpy2-mgcv":
        raise BackendError(f"Unsupported modeling backend: {backend}")
    return backend

