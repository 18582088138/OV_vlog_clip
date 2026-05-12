from __future__ import annotations

import json
import os
from pathlib import Path

from .models import TaskConfig

APP_DIR_NAME = "ov-video-editing-skills"
CONFIG_FILE_NAME = "gui-settings.json"


def default_settings_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def default_settings_path() -> Path:
    return default_settings_dir() / CONFIG_FILE_NAME


def load_task_config(settings_path: Path | None = None) -> TaskConfig:
    path = settings_path or default_settings_path()
    if not path.exists():
        return TaskConfig()

    payload = json.loads(path.read_text(encoding="utf-8"))
    config_payload = payload.get("task_config") if isinstance(payload, dict) else {}
    return TaskConfig.from_persisted_dict(config_payload if isinstance(config_payload, dict) else {})


def save_task_config(config: TaskConfig, settings_path: Path | None = None) -> Path:
    path = settings_path or default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"task_config": config.as_persisted_dict()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path