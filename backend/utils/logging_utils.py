"""Structured logging utilities for the NL2SQL pipeline."""

import logging
import sys
from typing import Any, Dict, Optional
from backend.core.config import settings


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger for the given module name.

    Usage:
        from backend.utils.logging_utils import get_logger
        logger = get_logger(__name__)
        logger.info("Agent started")
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    return logger


def log_agent_start(logger: logging.Logger, agent_name: str, state_summary: Optional[Dict[str, Any]] = None) -> None:
    """Log the start of an agent's execution."""
    msg = f"[{agent_name}] Starting"
    if state_summary:
        msg += f" | context={state_summary}"
    logger.info(msg)


def log_agent_end(logger: logging.Logger, agent_name: str, success: bool, details: str = "") -> None:
    """Log the completion of an agent's execution."""
    status = "SUCCESS" if success else "FAILURE"
    logger.info(f"[{agent_name}] {status}" + (f" | {details}" if details else ""))


def log_validation_result(logger: logging.Logger, syntax_valid: bool, schema_valid: bool, semantic_valid: bool) -> None:
    """Log the multi-dimensional validation result."""
    logger.info(
        f"[Validation] syntax={syntax_valid} schema={schema_valid} semantic={semantic_valid} "
        f"overall={syntax_valid and schema_valid and semantic_valid}"
    )


def log_security_decision(logger: logging.Logger, role: str, passed: bool, violations: list) -> None:
    """Log the security agent's decision."""
    if passed:
        logger.info(f"[Security] APPROVED for role='{role}'")
    else:
        logger.warning(f"[Security] REJECTED for role='{role}' | violations={violations}")
