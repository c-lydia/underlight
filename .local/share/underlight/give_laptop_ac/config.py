from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class FanCurve(BaseModel):
    points: list[list[int]] = Field(
        default_factory=lambda: [[40, 20], [55, 40], [70, 70], [85, 100]]
    )


class AlertsConfig(BaseModel):
    cpu_warn: int = 75
    cpu_crit: int = 85
    gpu_warn: int = 78
    gpu_crit: int = 83
    fan_stall_enabled: bool = True


class LoggingConfig(BaseModel):
    enabled: bool = False
    interval_seconds: int = 10
    format: str = "jsonl"
    output_dir: str = "~/.local/share/give_laptop_ac/logs"


class Settings(BaseModel):
    version: int = 1
    last_preset: str = "p-balanced"
    battery_limit: int = 80
    battery_start_limit: Optional[int] = None
    kbd_brightness: int = 2
    performance_mode: str = "comfort"
    fan_mode: str = "auto"
    cooler_boost: Optional[bool] = None
    theme: str = "default"
    fan_curves: dict[str, FanCurve] = Field(
        default_factory=lambda: {
            "cpu": FanCurve(),
            "gpu": FanCurve(),
        }
    )
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "give_laptop_ac"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def load_config() -> Settings:
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r") as f:
                data = yaml.safe_load(f) or {}
            return Settings(**data)
        except Exception:
            pass
    return Settings()


def save_config(settings: Settings) -> bool:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w") as f:
            yaml.safe_dump(settings.model_dump(), f, sort_keys=False)
        return True
    except Exception:
        return False


def reset_config() -> bool:
    try:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        return True
    except Exception:
        return False
