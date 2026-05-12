from __future__ import annotations

from importlib import resources
import json
import os
from pathlib import Path

from ..runtime import BIN_DIR, DEFAULT_MODEL_DIR
from .models import TaskConfig

APP_DIR_NAME = "ov-video-editing-skills"
CONFIG_FILE_NAME = "gui-settings.json"
PACKAGE_DEFAULT_CONFIG_NAME = "default_config.json"


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


def _default_ffmpeg_path() -> str:
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return str(BIN_DIR / ffmpeg_name)


def _render_payload(payload: dict) -> dict:
    rendered = json.loads(json.dumps(payload))
    replacements = {
        "{DEFAULT_MODEL_DIR}": str(DEFAULT_MODEL_DIR),
        "{DEFAULT_FFMPEG}": _default_ffmpeg_path(),
    }

    for key, value in list(rendered.items()):
        if isinstance(value, str):
            normalized = value
            for placeholder, replacement in replacements.items():
                normalized = normalized.replace(placeholder, replacement)
            rendered[key] = normalized
    return rendered


def describe_default_config_source(settings_path: Path | None = None) -> str:
    if settings_path:
        return str(Path(settings_path).resolve())
    return f"package://ov_video_editing_skills/gui/{PACKAGE_DEFAULT_CONFIG_NAME}"


def load_default_task_config(settings_path: Path | None = None) -> TaskConfig:
    if settings_path:
        path = Path(settings_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"默认配置文件不存在：{path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        normalized = payload.get("task_config", payload) if isinstance(payload, dict) else {}
        return TaskConfig.from_persisted_dict(_render_payload(normalized if isinstance(normalized, dict) else {}))

    payload = json.loads(resources.files(__package__).joinpath(PACKAGE_DEFAULT_CONFIG_NAME).read_text(encoding="utf-8"))
    return TaskConfig.from_persisted_dict(_render_payload(payload if isinstance(payload, dict) else {}))


def load_task_config(settings_path: Path | None = None) -> TaskConfig:
    return load_default_task_config(settings_path)


def save_task_config(config: TaskConfig, settings_path: Path | None = None) -> Path:
    path = settings_path or default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"task_config": config.as_persisted_dict()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path