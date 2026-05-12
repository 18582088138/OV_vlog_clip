from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Callable

from ..analyze_video import main as analyze_main
from ..compose_video import main as compose_main
from ..e2e import DEFAULT_REQUEST, derive_artifact_paths, extract_workspace_from_prepare_output, load_runtime_paths, main as e2e_main
from ..generate_storyboard import main as storyboard_main
from ..prepare_workspace import main as prepare_main
from ..runtime import BGM_DIR, current_python_path, current_conda_env_name, min_python_display, python_version_supported, safe_print
from .models import AppState, DiagnosticIssue, EnvironmentCheck, TaskConfig, TaskName, TaskResult, TaskStatus, WorkspaceArtifact

LogCallback = Callable[[str], None]
FINAL_OUTPUT_PREFIX = "Done. Final output: "
TEXT_PREVIEW_LIMIT = 12000


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


def _find_first_existing(workspace_dir: Path, *patterns: str) -> Path | None:
    for pattern in patterns:
        for candidate in sorted(workspace_dir.glob(pattern)):
            if candidate.exists():
                return candidate
    return None


def collect_workspace_artifacts(state: AppState, config: TaskConfig) -> list[WorkspaceArtifact]:
    workspace_path = state.workspace_path()
    if workspace_path is None or not workspace_path.exists():
        return []

    artifact_paths = state.artifact_paths or refresh_artifact_paths(state, config)
    result_artifacts = state.last_result.artifacts if state.last_result else {}

    mapped_paths = {
        "user_input": workspace_path / "user_input.txt",
        "brief": Path(artifact_paths.get("brief", "")) if artifact_paths.get("brief") else _find_first_existing(workspace_path, "*_brief.json", "creative_brief.json"),
        "analysis": Path(artifact_paths.get("analysis", "")) if artifact_paths.get("analysis") else _find_first_existing(workspace_path, "*_output_vlm.json", "output_vlm.json"),
        "storyboard": Path(artifact_paths.get("storyboard", "")) if artifact_paths.get("storyboard") else _find_first_existing(workspace_path, "*_storyboard.json", "storyboard.json"),
        "runtime": workspace_path / "runtime_env.json",
        "final_video": Path(result_artifacts.get("final_video", "")) if result_artifacts.get("final_video") else None,
    }
    labels = {
        "user_input": ("用户请求", "`prepare` 阶段生成的原始请求文本。"),
        "brief": ("Creative Brief", "自动抽取的时长、主题、节奏和保留要素。"),
        "analysis": ("VLM 分析结果", "视频分析阶段输出的结构化结果。"),
        "storyboard": ("Storyboard", "分镜与字幕、转场、BGM 选择结果。"),
        "runtime": ("运行时清单", "Python、模型、ffmpeg 等运行环境检查信息。"),
        "final_video": ("最终成片", "合成完成后生成的视频文件。"),
    }

    artifacts: list[WorkspaceArtifact] = []
    for key in ["user_input", "brief", "analysis", "storyboard", "runtime", "final_video"]:
        candidate = mapped_paths.get(key)
        path_str = str(candidate.resolve()) if isinstance(candidate, Path) and candidate.exists() else (str(candidate) if isinstance(candidate, Path) else "")
        artifacts.append(
            WorkspaceArtifact(
                key=key,
                label=labels[key][0],
                path=path_str,
                exists=bool(path_str) and Path(path_str).exists(),
                description=labels[key][1],
            )
        )
    return artifacts


def _truncate_preview(text: str, limit: int = TEXT_PREVIEW_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n...[内容已截断]"


def _build_storyboard_summary(payload: dict) -> str:
    clips = payload.get("clips") if isinstance(payload.get("clips"), list) else []
    outline = payload.get("story_outline") if isinstance(payload.get("story_outline"), dict) else {}
    lines = [
        "[Storyboard 结构预览]",
        f"分镜数量：{len(clips)}",
        f"主题：{outline.get('theme') or payload.get('theme') or '未提供'}",
        f"情绪弧线：{outline.get('emotional_arc') or payload.get('mood') or '未提供'}",
        f"必保留元素：{', '.join(outline.get('must_capture', [])) if isinstance(outline.get('must_capture'), list) else '未提供'}",
        "",
        "[分镜摘要]",
    ]

    for index, clip in enumerate(clips[:8], start=1):
        if not isinstance(clip, dict):
            continue
        start = clip.get("start") or clip.get("start_time") or "?"
        end = clip.get("end") or clip.get("end_time") or "?"
        subtitle = clip.get("subtitle") or clip.get("caption") or clip.get("text") or ""
        role = clip.get("narrative_role") or clip.get("role") or "未标注"
        transition = clip.get("transition") or "无"
        bgm = clip.get("bgm") or clip.get("bgm_choice") or "未指定"
        lines.extend(
            [
                f"{index}. [{start} - {end}] {role}",
                f"   字幕：{subtitle or '无'}",
                f"   转场：{transition} | BGM：{bgm}",
            ]
        )

    return "\n".join(lines)


def build_artifact_preview(artifact: WorkspaceArtifact) -> str:
    if not artifact.exists:
        return f"{artifact.label} 尚未生成。\n\n{artifact.description}"

    path = Path(artifact.path)
    if artifact.key == "final_video":
        return f"最终成片已生成：\n{path}\n\n可通过右侧视频区或独立弹窗播放。"

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"{artifact.label} 为二进制或非 UTF-8 文件：\n{path}"

    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return _truncate_preview(text)

        if artifact.key == "storyboard" and isinstance(payload, dict):
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            return _truncate_preview(_build_storyboard_summary(payload) + "\n\n[原始 JSON]\n" + pretty)

        return _truncate_preview(json.dumps(payload, ensure_ascii=False, indent=2))

    return _truncate_preview(text)


def _audio_file_extensions() -> tuple[str, ...]:
    return (".mp3", ".wav", ".flac", ".aac", ".m4a")


def collect_environment_checks(config: TaskConfig) -> list[EnvironmentCheck]:
    checks: list[EnvironmentCheck] = []

    python_detail = f"当前解释器：{current_python_path()}"
    python_suggestion = "" if python_version_supported() else f"请切换到 Python >= {min_python_display()} 的环境。"
    checks.append(
        EnvironmentCheck(
            key="python",
            label="Python 环境",
            status="ready" if python_version_supported() else "error",
            detail=python_detail,
            suggestion=python_suggestion,
            blocking=not python_version_supported(),
        )
    )

    conda_env = current_conda_env_name().strip()
    checks.append(
        EnvironmentCheck(
            key="conda_env",
            label="Conda 环境",
            status="ready" if conda_env else "warning",
            detail=f"当前环境：{conda_env or '未检测到 CONDA_DEFAULT_ENV'}",
            suggestion="如你依赖 conda 环境，请先执行 conda activate 目标环境。" if not conda_env else "",
            blocking=False,
        )
    )

    input_value = str(config.video_input or "").strip()
    input_exists = bool(input_value) and Path(input_value).exists()
    checks.append(
        EnvironmentCheck(
            key="video_input",
            label="输入数据",
            status="ready" if input_exists else ("warning" if not input_value else "error"),
            detail=input_value or "尚未选择视频目录或单视频文件。",
            suggestion="请选择输入视频目录或单个视频文件。" if not input_exists else "",
            blocking=bool(input_value) and not input_exists,
        )
    )

    model_path = Path(str(config.model_dir or "").strip()) if str(config.model_dir or "").strip() else None
    if config.skip_model:
        checks.append(
            EnvironmentCheck(
                key="model_dir",
                label="模型目录",
                status="skipped",
                detail="已启用 skip-model，本轮不检查模型目录。",
                suggestion="如需真实运行 analyze / e2e，请关闭 skip-model 并确认模型目录存在。",
                blocking=False,
            )
        )
    else:
        model_exists = bool(model_path and model_path.exists())
        checks.append(
            EnvironmentCheck(
                key="model_dir",
                label="模型目录",
                status="ready" if model_exists else "error",
                detail=str(model_path) if model_path else "主界面未设置模型路径。",
                suggestion="请在主界面选择模型目录，或使用 default config 中的默认路径。" if not model_exists else "",
                blocking=not model_exists,
            )
        )

    ffmpeg_value = str(config.ffmpeg_path or "").strip()
    ffmpeg_path = Path(ffmpeg_value) if ffmpeg_value else None
    ffprobe_path = None
    if ffmpeg_path is not None:
        ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        ffprobe_path = ffmpeg_path.with_name(ffprobe_name)
    if config.skip_ffmpeg:
        checks.append(
            EnvironmentCheck(
                key="ffmpeg",
                label="ffmpeg / ffprobe",
                status="skipped",
                detail="已启用 skip-ffmpeg，本轮不检查 ffmpeg / ffprobe。",
                suggestion="如需真实合成视频，请关闭 skip-ffmpeg 并确认 ffmpeg / ffprobe 可用。",
                blocking=False,
            )
        )
    else:
        ffmpeg_exists = bool(ffmpeg_path and ffmpeg_path.exists())
        ffprobe_exists = bool(ffprobe_path and ffprobe_path.exists())
        checks.append(
            EnvironmentCheck(
                key="ffmpeg",
                label="ffmpeg / ffprobe",
                status="ready" if ffmpeg_exists and ffprobe_exists else "error",
                detail=(
                    f"ffmpeg：{ffmpeg_path or '未设置'}\nffprobe：{ffprobe_path or '未推导'}"
                ),
                suggestion="请在 Settings 中指定 ffmpeg 路径，并确保同目录存在 ffprobe。" if not (ffmpeg_exists and ffprobe_exists) else "",
                blocking=not (ffmpeg_exists and ffprobe_exists),
            )
        )

    bgm_value = str(config.bgm_file or "").strip()
    if bgm_value:
        bgm_path = Path(bgm_value)
        checks.append(
            EnvironmentCheck(
                key="bgm",
                label="BGM 资源",
                status="ready" if bgm_path.exists() else "warning",
                detail=str(bgm_path),
                suggestion="指定的 BGM 文件不存在时，compose 会回退到无 BGM 或 storyboard 自带设置。" if not bgm_path.exists() else "",
                blocking=False,
            )
        )
    else:
        bgm_dir_exists = BGM_DIR.exists()
        has_bgm = bgm_dir_exists and any(path.suffix.lower() in _audio_file_extensions() for path in BGM_DIR.iterdir() if path.is_file())
        checks.append(
            EnvironmentCheck(
                key="bgm",
                label="BGM 资源",
                status="ready" if has_bgm else "warning",
                detail=f"默认目录：{BGM_DIR}",
                suggestion="当前未指定 BGM 文件；如需稳定背景音乐，建议在 Settings 中选择文件或向 resource/bgm/ 放入音频。" if not has_bgm else "",
                blocking=False,
            )
        )

    return checks


def format_environment_checks(checks: list[EnvironmentCheck]) -> str:
    if not checks:
        return "当前没有可展示的运行前检查结果。"
    icon_map = {"ready": "✓", "warning": "!", "error": "✗", "skipped": "-"}
    lines: list[str] = []
    for check in checks:
        lines.append(f"[{icon_map.get(check.status, '?')}] {check.label}")
        lines.append(f"  {check.detail}")
        if check.suggestion:
            lines.append(f"  建议：{check.suggestion}")
        lines.append("")
    return "\n".join(lines).rstrip()


def collect_diagnostic_issues(state: AppState, config: TaskConfig) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []
    for check in collect_environment_checks(config):
        if check.status == "error":
            issues.append(
                DiagnosticIssue(
                    key=f"preflight:{check.key}",
                    severity="error",
                    summary=f"运行前检查失败：{check.label}",
                    detail=check.detail,
                    suggestion=check.suggestion,
                )
            )
        elif check.status == "warning":
            issues.append(
                DiagnosticIssue(
                    key=f"preflight:{check.key}",
                    severity="warning",
                    summary=f"运行前提醒：{check.label}",
                    detail=check.detail,
                    suggestion=check.suggestion,
                )
            )

    result = state.last_result
    if result and not result.succeeded:
        combined = "\n".join(part for part in (result.stderr, result.stdout) if part)
        lowered = combined.lower()
        if "ffmpeg" in lowered or "ffprobe" in lowered:
            issues.insert(
                0,
                DiagnosticIssue(
                    key="task:ffmpeg",
                    severity="error",
                    summary="任务失败与 ffmpeg / ffprobe 相关",
                    detail="日志中检测到 ffmpeg 或 ffprobe 关键字。",
                    suggestion="请先在运行前检查面板确认 ffmpeg 路径和 ffprobe 是否同目录存在。",
                ),
            )
        if "模型目录" in combined or "model" in lowered:
            issues.insert(
                0,
                DiagnosticIssue(
                    key="task:model",
                    severity="error",
                    summary="任务失败与模型目录相关",
                    detail="日志中检测到模型目录缺失或模型加载失败的线索。",
                    suggestion="请检查主界面模型路径，或在 Settings 中启用/关闭 skip-model。",
                ),
            )
        if "no module named" in lowered or "pyside6" in lowered:
            issues.insert(
                0,
                DiagnosticIssue(
                    key="task:python-dependency",
                    severity="error",
                    summary="任务日志提示存在 Python 依赖缺失",
                    detail="日志中包含模块未找到信息。",
                    suggestion="请确认当前 Python 环境已经安装所需依赖，例如 GUI 需要 `PySide6`。",
                ),
            )

    deduped: list[DiagnosticIssue] = []
    seen: set[str] = set()
    for issue in issues:
        if issue.key in seen:
            continue
        seen.add(issue.key)
        deduped.append(issue)
    return deduped


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


def extract_final_video_path(stdout: str | None, stderr: str | None = None) -> Path | None:
    combined = "\n".join(part for part in (stdout, stderr) if part)
    for line in reversed([item.strip() for item in combined.splitlines() if item.strip()]):
        if line.startswith(FINAL_OUTPUT_PREFIX):
            return Path(line.removeprefix(FINAL_OUTPUT_PREFIX).strip())
    return None


def _update_state_from_result(state: AppState, config: TaskConfig, result: TaskResult) -> None:
    state.last_task = result.task_name
    state.last_result = result
    state.status = TaskStatus.SUCCEEDED if result.succeeded else TaskStatus.FAILED

    final_video = extract_final_video_path(result.stdout, result.stderr)
    final_video_artifact = {"final_video": str(final_video)} if final_video is not None else {}

    if result.task_name == TaskName.PREPARE and result.succeeded:
        workspace = extract_workspace_from_prepare_output(result.stdout, result.stderr)
        state.workspace_dir = str(workspace)
        runtime_paths = load_runtime_paths(workspace, config.video_input)
        state.artifact_paths = runtime_paths
        result.artifacts = runtime_paths | {"workspace": str(workspace)} | final_video_artifact
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
            result.artifacts = runtime_paths | {"workspace": str(workspace)} | final_video_artifact
    else:
        if state.workspace_dir:
            refresh_artifact_paths(state, config)
            result.artifacts = dict(state.artifact_paths) | final_video_artifact
            result.artifacts["workspace"] = state.workspace_dir
        elif final_video_artifact:
            result.artifacts = dict(result.artifacts) | final_video_artifact


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