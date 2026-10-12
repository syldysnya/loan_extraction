"""Hydra entry-point settings, shared by every command."""

from pathlib import Path

HYDRA_VERSION_BASE = "1.3"
# Absolute, so it works from entry points at any depth (Hydra resolves relative paths from the calling module).
CONFIG_PATH = str(Path(__file__).resolve().parents[1] / "conf")
CONFIG_NAME = "config"
