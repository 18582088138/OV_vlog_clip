from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, TextIO

MIN_PYTHON = (3, 10)
DEFAULT_MODEL_NAME = "Qwen2.5-VL-7B-Instruct-int4"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
RESOURCE_DIR = PROJECT_DIR / "resource"
BGM_DIR = RESOURCE_DIR / "bgm"
BIN_DIR = PROJECT_DIR / "bin"
MODELS_DIR = PROJECT_DIR / "models"
DEFAULT_MODEL_DIR = MODELS_DIR / DEFAULT_MODEL_NAME
REQUIREMENTS_FILE = PROJECT_DIR / "requirements.txt"


def min_python_display() -> str:
    return f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"


def python_version_supported(version_info: tuple[int, int] | None = None) -> bool:
    if version_info is None:
        version_info = (sys.version_info.major, sys.version_info.minor)
    return version_info >= MIN_PYTHON


def assert_host_python_supported() -> None:
    if python_version_supported():
        return
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    raise RuntimeError(
        f"当前 Python 版本 {version} 不受支持，需要 Python >= {min_python_display()}。"
    )


def current_python_path() -> Path:
    return Path(sys.executable).resolve()


def current_conda_env_name() -> str:
    return os.environ.get("CONDA_DEFAULT_ENV", "")


def safe_console_text(text: object) -> str:
    return str(text)


def safe_print(*values: object, sep: str = " ", end: str = "\n", file: TextIO | None = None) -> None:
    stream = file or sys.stdout
    text = sep.join(safe_console_text(value) for value in values) + end
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        stream.write(text)
    except UnicodeEncodeError:
        fallback = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore")
        stream.write(fallback)
    stream.flush()


def ensure_local_venv() -> Path:
    assert_host_python_supported()
    return current_python_path()


def ensure_local_requirements(force: bool = False) -> Path:
    del force
    assert_host_python_supported()
    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError(f"requirements.txt 不存在：{REQUIREMENTS_FILE}")
    safe_print(f"[python] 使用当前解释器：{current_python_path()}")
    env_name = current_conda_env_name()
    if env_name:
        safe_print(f"[python] 当前 conda 环境：{env_name}")
    else:
        safe_print("[python] 未检测到 conda 环境变量，请确认已激活目标环境。")
    return current_python_path()


def running_in_local_venv() -> bool:
    return True


def maybe_reexec_in_local_venv(module_name: str) -> None:
    del module_name
    return


def runtime_summary() -> dict[str, str]:
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    return {
        "project_dir": str(PROJECT_DIR),
        "python_executable": str(current_python_path()),
        "conda_env_name": current_conda_env_name(),
        "requirements_file": str(REQUIREMENTS_FILE),
        "resource_dir": str(RESOURCE_DIR),
        "bgm_dir": str(BGM_DIR),
        "bin_dir": str(BIN_DIR),
        "ffmpeg": str(BIN_DIR / ffmpeg_name),
        "ffprobe": str(BIN_DIR / ffprobe_name),
        "model_dir": str(DEFAULT_MODEL_DIR),
        "min_python": min_python_display(),
    }


def write_runtime_manifest(workspace_dir: Path, extra: Optional[dict[str, object]] = None) -> Path:
    manifest_path = workspace_dir / "runtime_env.json"
    payload: dict[str, object] = runtime_summary() | {"workspace_dir": str(workspace_dir)}
    if extra:
        payload.update(extra)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
