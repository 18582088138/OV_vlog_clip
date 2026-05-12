from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Callable

from ..analyze_video import main as analyze_main
from ..compose_video import main as compose_main
from ..e2e import DEFAULT_REQUEST, derive_artifact_paths, extract_workspace_from_prepare_output, load_runtime_paths, main as e2e_main
from ..generate_storyboard import main as storyboard_main
from ..prepare_workspace import main as prepare_main
from ..runtime import safe_print
from .models import AppState, TaskConfig, TaskName, TaskResult, TaskStatus

LogCallback = Callable[[str], None]


class _CallbackWriter(io.StringIO):
    def __init__(self, callback: LogCallback | None, stream) -> None:
        super().__init__()
        self.callback = callback
        self.stream = stream
        self._buffer = ""

    def write(self, text: str) -> int:
        self.stream.write(text)
        self.stream.flush()
        self._buffer += text
        if self.callback:
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self.callback(line)
        return super().write(text)

    def flush_pending(self) -> None:
        if self.callback and self._buffer:
            self.callback(self._buffer)
            self._buffer = ""


def _emit(log_callback: LogCallback | None, text: str) -> None:
    if log_callback:
        log_callback(str(text))


def _invoke_handler(task_name: TaskName, handler, argv: list[str], log_callback: LogCallback | None = None) -> TaskResult:
    original_argv = sys.argv[:]
    stdout_buffer = _CallbackWriter(log_callback, sys.stdout)
    stderr_buffer = _CallbackWriter(log_callback, sys.stderr)
    try:
        sys.argv = [original_argv[0], *argv]
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            returncode = int(handler())
    finally:
        sys.argv = original_argv
        stdout_buffer.flush_pending()
        stderr_buffer.flush_pending()

    return TaskResult(
        task_name=task_name,
        args=argv,
        returncode=returncode,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


def _optional_kv(flag: str, value: str) -> list[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return []
    return [flag, normalized]


def build_prepare_args(config: TaskConfig) -> list[str]:
    args = [
        "--video-dir",
        str(Path(config.video_input).resolve()),
        "--user-request",
        config.user_request or DEFAULT_REQUEST,
    ]
    if config.ignore_existing_analysis:
        args.append("--ignore-existing-analysis")
    if config.skip_ffmpeg:
        args.append("--skip-ffmpeg")
    if config.skip_model:
        args.append("--skip-model")
    return args


def build_analyze_args(config: TaskConfig, state: AppState) -> list[str]:
    args = ["--video-dir", str(Path(config.video_input).resolve())]
    brief = resolve_brief_path(config, state)
    analysis_path = resolve_analysis_path(config, state)
    args.extend(_optional_kv("--brief", brief))
    args.extend(_optional_kv("--output", analysis_path))
    args.extend(_optional_kv("--model-dir", config.model_dir))
    args.extend(_optional_kv("--device", config.device))
    return args


def build_storyboard_args(config: TaskConfig, state: AppState) -> list[str]:
    args = ["--analysis", resolve_analysis_path(config, state)]
    storyboard_path = resolve_storyboard_path(config, state)
    brief = resolve_brief_path(config, state)
    args.extend(_optional_kv("--output", storyboard_path))
    args.extend(_optional_kv("--brief", brief))
    args.extend(_optional_kv("--bgm-style", config.bgm_style))
    args.extend(_optional_kv("--bgm-file", config.bgm_file))
    return args


def build_compose_args(config: TaskConfig, state: AppState) -> list[str]:
    args = ["--storyboard", resolve_storyboard_path(config, state)]
    args.extend(_optional_kv("--output-dir", resolve_output_dir(config, state)))
    args.extend(_optional_kv("--ffmpeg", config.ffmpeg_path))
    args.extend(_optional_kv("--font-file", config.font_file))
    return args


def build_e2e_args(config: TaskConfig) -> list[str]:
    args = [
        "--video-dir",
        str(Path(config.video_input).resolve()),
        "--user-request",
        config.user_request or DEFAULT_REQUEST,
    ]
    args.extend(_optional_kv("--output-dir", config.output_dir))
    args.extend(_optional_kv("--model-dir", config.model_dir))
    args.extend(_optional_kv("--device", config.device))
    args.extend(_optional_kv("--bgm-file", config.bgm_file))
    args.extend(_optional_kv("--bgm-style", config.bgm_style))
    args.extend(_optional_kv("--ffmpeg", config.ffmpeg_path))
    args.extend(_optional_kv("--font-file", config.font_file))
    if config.ignore_existing_analysis:
        args.append("--ignore-existing-analysis")
    if config.skip_ffmpeg:
        args.append("--skip-ffmpeg")
    if config.skip_model:
        args.append("--skip-model")
    return args


def ensure_config_ready(config: TaskConfig) -> None:
    if not str(config.video_input or "").strip():
        raise ValueError("请先选择视频目录或单个视频文件。")


def refresh_artifact_paths(state: AppState, config: TaskConfig) -> dict[str, str]:
    workspace_dir = state.workspace_dir or resolve_output_dir(config, state) or "<workspace_from_prepare>"
    artifact_paths = derive_artifact_paths(config.video_input, workspace_dir)
    state.artifact_paths = artifact_paths
    return artifact_paths


def resolve_brief_path(config: TaskConfig, state: AppState) -> str:
    if str(config.brief_path or "").strip():
        return str(Path(config.brief_path).resolve())
    artifact_paths = state.artifact_paths or refresh_artifact_paths(state, config)
    return artifact_paths.get("brief", "")


def resolve_analysis_path(config: TaskConfig, state: AppState) -> str:
    if str(config.analysis_path or "").strip():
        return str(Path(config.analysis_path).resolve())
    artifact_paths = state.artifact_paths or refresh_artifact_paths(state, config)
    return artifact_paths.get("analysis", "")


def resolve_storyboard_path(config: TaskConfig, state: AppState) -> str:
    if str(config.storyboard_path or "").strip():
        return str(Path(config.storyboard_path).resolve())
    artifact_paths = state.artifact_paths or refresh_artifact_paths(state, config)
    return artifact_paths.get("storyboard", "")


def resolve_output_dir(config: TaskConfig, state: AppState) -> str:
    if str(config.output_dir or "").strip():
        return str(Path(config.output_dir).resolve())
    return state.workspace_dir


def _update_state_from_result(state: AppState, config: TaskConfig, result: TaskResult) -> None:
    state.last_task = result.task_name
    state.last_result = result
    state.status = TaskStatus.SUCCEEDED if result.succeeded else TaskStatus.FAILED

    if result.task_name == TaskName.PREPARE and result.succeeded:
        workspace = extract_workspace_from_prepare_output(result.stdout, result.stderr)
        state.workspace_dir = str(workspace)
        runtime_paths = load_runtime_paths(workspace, config.video_input)
        state.artifact_paths = runtime_paths
        result.artifacts = runtime_paths | {"workspace": str(workspace)}
    elif result.task_name == TaskName.E2E and result.succeeded:
        workspace = None
        try:
            workspace = extract_workspace_from_prepare_output(result.stdout, result.stderr)
        except Exception:
            workspace = None
        if workspace:
            state.workspace_dir = str(workspace)
            runtime_paths = load_runtime_paths(workspace, config.video_input)
            state.artifact_paths = runtime_paths
            result.artifacts = runtime_paths | {"workspace": str(workspace)}
    else:
        if state.workspace_dir:
            refresh_artifact_paths(state, config)
            result.artifacts = dict(state.artifact_paths)
            result.artifacts["workspace"] = state.workspace_dir


class GuiTaskService:
    def __init__(self, state: AppState) -> None:
        self.state = state

    def run(self, task_name: TaskName, config: TaskConfig, log_callback: LogCallback | None = None) -> TaskResult:
        ensure_config_ready(config)
        self.state.status = TaskStatus.RUNNING
        self.state.last_task = task_name

        _emit(log_callback, f"[gui] 开始执行：{task_name.value}")

        if task_name == TaskName.PREPARE:
            result = _invoke_handler(task_name, prepare_main, build_prepare_args(config), log_callback)
        elif task_name == TaskName.ANALYZE:
            result = _invoke_handler(task_name, analyze_main, build_analyze_args(config, self.state), log_callback)
        elif task_name == TaskName.STORYBOARD:
            result = _invoke_handler(task_name, storyboard_main, build_storyboard_args(config, self.state), log_callback)
        elif task_name == TaskName.COMPOSE:
            result = _invoke_handler(task_name, compose_main, build_compose_args(config, self.state), log_callback)
        elif task_name == TaskName.E2E:
            result = _invoke_handler(task_name, e2e_main, build_e2e_args(config), log_callback)
        else:
            raise ValueError(f"不支持的任务类型：{task_name}")

        _update_state_from_result(self.state, config, result)
        _emit(log_callback, f"[gui] 执行结束：{task_name.value} -> rc={result.returncode}")
        return result


def summarize_state_for_debug(state: AppState) -> str:
    payload = {
        "status": state.status.value,
        "workspace_dir": state.workspace_dir,
        "last_task": state.last_task.value if state.last_task else "",
        "artifact_paths": state.artifact_paths,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)