# Verkada Utilities
# This module provides utility functions for ProjectDecommission.
import os
from typing import Optional


def get_env_var(key: str, default: Optional[str] = None) -> str:
    """Safely gets a required environment variable with optional default."""
    value = os.environ.get(key, default)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return value
