"""Logging utilities for ArboMAP pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Set up a logger with console and optional file output.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        log_file: Optional path to log file
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger


def log_step(logger: logging.Logger, step_name: str, details: str = "") -> None:
    """Log a pipeline step with consistent formatting.
    
    Args:
        logger: Logger instance
        step_name: Name of the step
        details: Optional details about the step
    """
    logger.info(f"=== {step_name} ===")
    if details:
        logger.info(f"  {details}")


def log_error_with_context(
    logger: logging.Logger,
    error: Exception,
    context: str = "",
) -> None:
    """Log an error with context information.
    
    Args:
        logger: Logger instance
        error: Exception that occurred
        context: Additional context about where/why the error occurred
    """
    logger.error(f"ERROR in {context}: {type(error).__name__}: {error}")
    logger.debug("Full traceback:", exc_info=error)

