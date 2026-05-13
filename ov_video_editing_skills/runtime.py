from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, TextIO, Callable
import time
import contextlib
import importlib.resources as importlib_resources

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None

MIN_PYTHON = (3, 10)
DEFAULT_MODEL_NAME = "Qwen2.5-VL-7B-Instruct-int4"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
REQUIREMENTS_FILE = PROJECT_DIR / "requirements.txt"


def _candidate_resource_score(candidate: Path) -> tuple[int, int]:
    expected_dirs = [candidate / "bin", candidate / "resource", candidate / "models"]
    expected_count = sum(path.exists() for path in expected_dirs)
    marker_count = sum((candidate / name).exists() for name in ["pyproject.toml", "run.py", "requirements.txt"])
    return expected_count, marker_count


def resolve_app_dir(
    *,
    executable_path: Path | None = None,
    frozen: bool | None = None,
    project_dir: Path | None = None,
    package_dir: Path | None = None,
) -> Path:
    resolved_project_dir = Path(project_dir).resolve() if project_dir else PROJECT_DIR
    resolved_package_dir = Path(package_dir).resolve() if package_dir else PACKAGE_DIR
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not is_frozen:
        return resolved_project_dir

    executable_dir = Path(executable_path).resolve().parent if executable_path else Path(sys.executable).resolve().parent
    candidates: list[Path] = []
    current = executable_dir
    for _ in range(6):
        if current not in candidates:
            candidates.append(current)
        if current.parent == current:
            break
        current = current.parent

    if resolved_project_dir not in candidates:
        candidates.append(resolved_project_dir)
    package_project_dir = resolved_package_dir.parent
    if package_project_dir not in candidates:
        candidates.append(package_project_dir)

    best_candidate = executable_dir
    best_score = (-1, -1)
    best_distance = 10**9
    for index, candidate in enumerate(candidates):
        score = _candidate_resource_score(candidate)
        if score <= (0, 0):
            continue
        if score > best_score or (score == best_score and index < best_distance):
            best_candidate = candidate
            best_score = score
            best_distance = index

    return best_candidate


APP_DIR = resolve_app_dir()
RESOURCE_DIR = APP_DIR / "resource"
BGM_DIR = RESOURCE_DIR / "bgm"
BIN_DIR = APP_DIR / "bin"
MODELS_DIR = APP_DIR / "models"
DEFAULT_MODEL_DIR = MODELS_DIR / DEFAULT_MODEL_NAME


def running_as_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


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
    stream = file if file is not None else sys.stdout
    if stream is None:
        stream = sys.__stdout__ or sys.__stderr__
    if stream is None:
        return
    text = sep.join(safe_console_text(value) for value in values) + end
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        stream.write(text)
    except UnicodeEncodeError:
        fallback = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore")
        stream.write(fallback)
    stream.flush()


def hidden_subprocess_kwargs() -> dict[str, object]:
    """
    Windows下用于隐藏所有ffmpeg/ffprobe等子进程窗口的参数。
    【注意】所有涉及ffmpeg/ffprobe的subprocess调用必须加上**hidden_subprocess_kwargs()**，否则GUI/打包环境下会弹黑框。
    """
    if os.name != "nt":
        return {}

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)

    kwargs: dict[str, object] = {
        "creationflags": creationflags,
        "stdin": subprocess.DEVNULL,
    }
    startupinfo_factory = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_factory is not None:
        startupinfo = startupinfo_factory()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
    return kwargs


def ensure_local_venv() -> Path:
    assert_host_python_supported()
    return current_python_path()


def ensure_local_requirements(force: bool = False) -> Path:
    del force
    assert_host_python_supported()
    if running_as_packaged_app():
        safe_print(f"[python] 使用打包后的可执行文件：{current_python_path()}")
        safe_print("[python] 当前为独立打包运行时，Python 依赖已随 EXE 一起分发。")
        return current_python_path()
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
        "deployment_mode": "packaged-exe" if running_as_packaged_app() else "python-source",
        "project_dir": str(PROJECT_DIR),
        "app_dir": str(APP_DIR),
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


def _get_process_memory_mb() -> float:
    """返回当前进程的常驻内存（MB），尽量使用 psutil，失败则返回 0."""
    try:
        if psutil is not None:
            p = psutil.Process()
            rss = getattr(p.memory_info(), "rss", 0)
            return float(rss) / 1024.0 / 1024.0
        # fallback: try resource (best-effort, may not be available on Windows)
        import resource  # type: ignore

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is kilobytes on Linux, bytes on some platforms—treat as KB
        return float(getattr(usage, "ru_maxrss", 0)) / 1024.0
    except Exception:
        return 0.0


@contextlib.contextmanager
def task_performance(task_name: str, log_callback: Optional[Callable[[str], None]] = None):
    """Context manager: 记录任务运行时间与近似内存，结束时打印摘要。"""
    start = time.time()
    start_mem = _get_process_memory_mb()
    try:
        yield
    finally:
        end = time.time()
        end_mem = _get_process_memory_mb()
        elapsed = end - start
        mem_used = max(0.0, end_mem - start_mem)
        # 根据 log_level 决定是否打印性能摘要（仅 DEBUG/INFO 时打印）
        try:
            env_level = os.environ.get("OV_LOG_LEVEL")
            if env_level:
                effective = env_level.strip().upper()
            else:
                # 尝试读取打包随带的 GUI default_config.json
                effective = "INFO"
                try:
                    cfg_text = importlib_resources.files("ov_video_editing_skills.gui").joinpath("default_config.json").read_text(encoding="utf-8")
                    import json as _json

                    payload = _json.loads(cfg_text)
                    if isinstance(payload, dict) and payload.get("log_level"):
                        effective = str(payload.get("log_level") or "INFO").strip().upper()
                except Exception:
                    pass

            if effective in ("DEBUG", "INFO"):
                message = f"[PERF] {task_name} elapsed={elapsed:.2f}s, mem_delta={mem_used:.2f}MB, mem_end={end_mem:.2f}MB"
                safe_print(message)
                try:
                    if log_callback:
                        log_callback(message)
                except Exception:
                    pass
        except Exception:
            # 忽略打印错误
            pass
