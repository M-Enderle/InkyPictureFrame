"""Client configuration defaults.

This module provides default values and helpers for loading simple overrides
from environment variables. The polling client reads these values but also
accepts CLI overrides.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    host: str = os.environ.get("INKY_FRAME_HOST", "127.0.0.1")
    port: int = int(os.environ.get("INKY_FRAME_PORT", "8000"))
    poll_interval: int = int(os.environ.get("INKY_FRAME_POLL_INTERVAL", "60"))


def load() -> Config:
    """Return a Config instance using environment overrides."""
    return Config()
