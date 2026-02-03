"""Config loading utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

try:
    import yaml
except ImportError as exc:  # pragma: no cover - handled at runtime
    yaml = None
    _yaml_import_error = exc


class ConfigError(RuntimeError):
    """Raised when config loading or validation fails."""


@dataclass(frozen=True)
class Config:
    """Typed wrapper for config dictionary."""

    data: Dict[str, Any]


def load_config(path: str) -> Config:
    """Load YAML config from disk."""
    if yaml is None:
        raise ConfigError(
            "PyYAML is required to load config files."
        ) from _yaml_import_error

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ConfigError("Config file must parse to a mapping.")

    return Config(data=data)

