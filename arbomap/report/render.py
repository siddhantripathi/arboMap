"""Report rendering entrypoints."""

from typing import Dict, Any


def render_report(outputs: Dict[str, Any], config: Dict[str, Any]) -> None:
    """Render HTML/PDF reports from serialized model outputs."""
    raise NotImplementedError("Report rendering is not implemented yet.")

