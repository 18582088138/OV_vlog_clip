from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .analyze_video import main as analyze_main
from .compose_video import main as compose_main
from .creative_brief import (
    build_analysis_file_name,
    build_brief_file_name,
    build_storyboard_file_name,
    derive_artifact_base_name,
)
from .generate_storyboard import main as storyboard_main
from .prepare_workspace import main as prepare_main
from .runtime import safe_print

DEFAULT_REQUEST = "做一个30秒的视频总结vlog"
DEFAULT_VIDEO_CANDIDATES = (
    "videos/2022yunqidahui.mp4",
    "videos",
)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv"}
WORKSPACE_PLACEHOLDER = "<workspace_from_prepare>"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_video_input(repo_root: Path) -> Path:
    for candidate in DEFAULT_VIDEO_CANDIDATES:
        resolved = repo_root / candidate
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        "未找到默认测试素材，请通过 --video-dir 显式传入视频目录或单个视频文件。"
    )


def resolve_video_input(video_input: Path) -> tuple[Path, list[Path]]:
    if video_input.is_file():
        if video_input.suffix.lower() not in VIDEO_EXTENSIONS:
            raise FileNotFoundError(f"不支持的视频文件格式：{video_input}")
        return video_input.parent, [video_input]

    if video_input.is_dir():
        videos = [
            path
            for path in sorted(video_input.iterdir())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not videos:
            raise FileNotFoundError(f"目录中未找到视频文件：{video_input}")
        return video_input, videos

    raise FileNotFoundError(f"视频目录或文件不存在：{video_input}")


def derive_artifact_paths(video_input: str | Path | None, workspace_dir: str | Path) -> dict[str, str]:
    repo_root = project_root()
    resolved_video_input = Path(video_input).resolve() if video_input else default_video_input(repo_root)
    video_root, videos = resolve_video_input(resolved_video_input)
    artifact_base_name = derive_artifact_base_name(video_root, videos)
    workspace_str = str(workspace_dir)
    return {
        "artifact_base_name": artifact_base_name,
        "brief": str(Path(workspace_str) / build_brief_file_name(artifact_base_name)),
        "analysis": str(Path(workspace_str) / build_analysis_file_name(artifact_base_name)),
        "storyboard": str(Path(workspace_str) / build_storyboard_file_name(artifact_base_name)),
    }


def build_prepare_command(
    repo_root: Path,
    python_executable: str | Path,
    video_dir: str | Path | None = None,
    user_request: str = DEFAULT_REQUEST,
    ignore_existing_analysis: bool = False,
    skip_ffmpeg: bool = False,
    skip_model: bool = False,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    target = Path(video_dir).resolve() if video_dir else default_video_input(repo_root)
    command = [
        str(python_executable),
        "run.py",
        "prepare",
        "--video-dir",
        str(target),
        "--user-request",
        user_request,
    ]
    if ignore_existing_analysis:
        command.append("--ignore-existing-analysis")
    if skip_ffmpeg:
        command.append("--skip-ffmpeg")
    if skip_model:
        command.append("--skip-model")
    if extra_args:
        command.extend(extra_args)
    return command


def build_analyze_command(
    repo_root: Path,
    python_executable: str | Path,
    video_dir: str | Path | None = None,
    brief: str | Path | None = None,
    output: str | Path | None = None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    target = Path(video_dir).resolve() if video_dir else default_video_input(repo_root)
    command = [
        str(python_executable),
        "run.py",
        "analyze",
        "--video-dir",
        str(target),
    ]
    if brief:
        command.extend(["--brief", str(Path(brief))])
    if output:
        command.extend(["--output", str(Path(output))])
    if extra_args:
        command.extend(extra_args)
    return command


def build_storyboard_command(
    python_executable: str | Path,
    analysis: str | Path,
    output: str | Path | None = None,
    brief: str | Path | None = None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    command = [
        str(python_executable),
        "run.py",
        "storyboard",
        "--analysis",
        str(Path(analysis)),
    ]
    if output:
        command.extend(["--output", str(Path(output))])
    if brief:
        command.extend(["--brief", str(Path(brief))])
    if extra_args:
        command.extend(extra_args)
    return command


def build_compose_command(
    python_executable: str | Path,
    storyboard: str | Path,
    output_dir: str | Path | None = None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    command = [
        str(python_executable),
        "run.py",
        "compose",
        "--storyboard",
        str(Path(storyboard)),
    ]
    if output_dir:
        command.extend(["--output-dir", str(Path(output_dir))])
    if extra_args:
        command.extend(extra_args)
    return command


def build_e2e_commands(
    repo_root: Path,
    python_executable: str | Path,
    video_dir: str | Path | None = None,
    user_request: str = DEFAULT_REQUEST,
    ignore_existing_analysis: bool = False,
    skip_ffmpeg: bool = False,
    skip_model: bool = False,
    output_dir: str | Path | None = None,
    workspace_dir: str | Path = WORKSPACE_PLACEHOLDER,
    prepare_extra_args: Sequence[str] | None = None,
    analyze_extra_args: Sequence[str] | None = None,
    storyboard_extra_args: Sequence[str] | None = None,
    compose_extra_args: Sequence[str] | None = None,
) -> dict[str, list[str] | dict[str, str]]:
    artifact_paths = derive_artifact_paths(video_dir, workspace_dir)
    prepare_command = build_prepare_command(
        repo_root=repo_root,
        python_executable=python_executable,
        video_dir=video_dir,
        user_request=user_request,
        ignore_existing_analysis=ignore_existing_analysis,
        skip_ffmpeg=skip_ffmpeg,
        skip_model=skip_model,
        extra_args=prepare_extra_args,
    )
    analyze_command = build_analyze_command(
        repo_root=repo_root,
        python_executable=python_executable,
        video_dir=video_dir,
        brief=artifact_paths["brief"],
        output=artifact_paths["analysis"],
        extra_args=analyze_extra_args,
    )
    storyboard_command = build_storyboard_command(
        python_executable=python_executable,
        analysis=artifact_paths["analysis"],
        output=artifact_paths["storyboard"],
        brief=artifact_paths["brief"],
        extra_args=storyboard_extra_args,
    )
    compose_command = build_compose_command(
        python_executable=python_executable,
        storyboard=artifact_paths["storyboard"],
        output_dir=output_dir or workspace_dir,
        extra_args=compose_extra_args,
    )
    return {
        "paths": artifact_paths,
        "prepare": prepare_command,
        "analyze": analyze_command,
        "storyboard": storyboard_command,
        "compose": compose_command,
    }


def build_prepare_args(
    video_dir: str | Path | None,
    user_request: str,
    ignore_existing_analysis: bool,
    skip_ffmpeg: bool,
    skip_model: bool,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    target = Path(video_dir).resolve() if video_dir else default_video_input(project_root())
    args = ["--video-dir", str(target), "--user-request", user_request]
    if ignore_existing_analysis:
        args.append("--ignore-existing-analysis")
    if skip_ffmpeg:
        args.append("--skip-ffmpeg")
    if skip_model:
        args.append("--skip-model")
    if extra_args:
        args.extend(extra_args)
    return args


def build_analyze_args(
    video_dir: str | Path | None,
    brief: str | Path | None,
    output: str | Path | None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    target = Path(video_dir).resolve() if video_dir else default_video_input(project_root())
    args = ["--video-dir", str(target)]
    if brief:
        args.extend(["--brief", str(Path(brief))])
    if output:
        args.extend(["--output", str(Path(output))])
    if extra_args:
        args.extend(extra_args)
    return args


def build_storyboard_args(
    analysis: str | Path,
    output: str | Path | None,
    brief: str | Path | None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    args = ["--analysis", str(Path(analysis))]
    if output:
        args.extend(["--output", str(Path(output))])
    if brief:
        args.extend(["--brief", str(Path(brief))])
    if extra_args:
        args.extend(extra_args)
    return args


def build_compose_args(
    storyboard: str | Path,
    output_dir: str | Path | None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    args = ["--storyboard", str(Path(storyboard))]
    if output_dir:
        args.extend(["--output-dir", str(Path(output_dir))])
    if extra_args:
        args.extend(extra_args)
    return args


def _kv_args(flag: str, value: str | None) -> list[str]:
    if value is None or value == "":
        return []
    return [flag, value]


@dataclass
class StepResult:
    returncode: int
    stdout: str
    stderr: str


class TeeBuffer(io.StringIO):
    def __init__(self, mirror) -> None:
        super().__init__()
        self.mirror = mirror

    def write(self, text: str) -> int:
        self.mirror.write(text)
        self.mirror.flush()
        return super().write(text)


def run_step(handler: Callable[[], int], argv: list[str], label: str) -> StepResult:
    safe_print(f"[test_e2e] running {label}: {label} {subprocess.list2cmdline(argv)}")
    original_argv = sys.argv[:]
    stdout_buffer = TeeBuffer(sys.stdout)
    stderr_buffer = TeeBuffer(sys.stderr)
    try:
        sys.argv = [label, *argv]
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            return_code = int(handler())
    finally:
        sys.argv = original_argv
    return StepResult(return_code, stdout_buffer.getvalue(), stderr_buffer.getvalue())


def extract_workspace_from_prepare_output(stdout: str | None, stderr: str | None = None) -> Path:
    combined_output = "\n".join(part for part in (stdout, stderr) if part)
    for line in reversed([item.strip() for item in combined_output.splitlines() if item.strip()]):
        candidate = Path(line)
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError("无法从 prepare 输出中解析工作区目录。")


def load_runtime_paths(workspace_dir: Path, fallback_video_dir: str | Path | None) -> dict[str, str]:
    manifest_path = workspace_dir / "runtime_env.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"未找到 runtime manifest：{manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    fallback_paths = derive_artifact_paths(fallback_video_dir, workspace_dir)
    return {
        "artifact_base_name": str(payload.get("artifact_base_name") or fallback_paths["artifact_base_name"]),
        "brief": str(payload.get("creative_brief") or fallback_paths["brief"]),
        "analysis": str(payload.get("workspace_analysis") or fallback_paths["analysis"]),
        "storyboard": fallback_paths["storyboard"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键执行 prepare/analyze/storyboard/compose 的 E2E 测试脚本")
    parser.add_argument("--video-dir", default=None, help="视频目录或单个视频文件；未传时自动尝试仓库内默认素材")
    parser.add_argument("--user-request", default=DEFAULT_REQUEST, help="传给 prepare 的用户需求描述")
    parser.add_argument("--output-dir", default=None, help="compose 阶段的可选输出目录；未传时默认使用工作区")
    parser.add_argument("--python", dest="python_executable", default=sys.executable, help="仅用于 dry-run 打印的解释器路径")
    parser.add_argument("--ignore-existing-analysis", action="store_true", help="透传给 prepare，忽略已有分析结果")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="prepare 阶段跳过 ffmpeg / ffprobe 检查")
    parser.add_argument("--skip-model", action="store_true", help="prepare 阶段跳过默认模型目录检查")
    parser.add_argument("--model-dir", default=None, help="透传给 analyze 的模型目录，可传仓库外绝对路径")
    parser.add_argument("--device", default=None, help="透传给 analyze 的设备，例如 CPU / GPU")
    parser.add_argument("--bgm-file", default=None, help="透传给 storyboard 的 BGM 文件名或绝对路径")
    parser.add_argument("--bgm-style", default=None, help="透传给 storyboard 的 BGM 风格标签")
    parser.add_argument("--ffmpeg", default=None, help="透传给 compose 的 ffmpeg 绝对路径或 PATH 命令名")
    parser.add_argument("--font-file", default=None, help="透传给 compose 的字体文件绝对路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印完整 E2E 命令链，不实际执行")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = project_root()
    analyze_extra_args = _kv_args("--model-dir", args.model_dir) + _kv_args("--device", args.device)
    storyboard_extra_args = _kv_args("--bgm-file", args.bgm_file) + _kv_args("--bgm-style", args.bgm_style)
    compose_extra_args = _kv_args("--ffmpeg", args.ffmpeg) + _kv_args("--font-file", args.font_file)

    commands = build_e2e_commands(
        repo_root=repo_root,
        python_executable=args.python_executable,
        video_dir=args.video_dir,
        user_request=args.user_request,
        ignore_existing_analysis=args.ignore_existing_analysis,
        skip_ffmpeg=args.skip_ffmpeg,
        skip_model=args.skip_model,
        output_dir=args.output_dir,
        analyze_extra_args=analyze_extra_args,
        storyboard_extra_args=storyboard_extra_args,
        compose_extra_args=compose_extra_args,
    )

    safe_print("[test_e2e] repo:", repo_root)
    safe_print("[test_e2e] artifact paths:", json.dumps(commands["paths"], ensure_ascii=False, indent=2))
    for label in ("prepare", "analyze", "storyboard", "compose"):
        safe_print(f"[test_e2e] {label}: {subprocess.list2cmdline(commands[label])}")

    if args.dry_run:
        return 0

    prepare_args = build_prepare_args(
        video_dir=args.video_dir,
        user_request=args.user_request,
        ignore_existing_analysis=args.ignore_existing_analysis,
        skip_ffmpeg=args.skip_ffmpeg,
        skip_model=args.skip_model,
    )
    prepare_completed = run_step(prepare_main, prepare_args, "prepare")
    if prepare_completed.returncode != 0:
        return int(prepare_completed.returncode)

    workspace_dir = extract_workspace_from_prepare_output(prepare_completed.stdout, prepare_completed.stderr)
    runtime_paths = load_runtime_paths(workspace_dir, args.video_dir)

    analyze_args = build_analyze_args(
        video_dir=args.video_dir,
        brief=runtime_paths["brief"],
        output=runtime_paths["analysis"],
        extra_args=analyze_extra_args,
    )
    analyze_completed = run_step(analyze_main, analyze_args, "analyze")
    if analyze_completed.returncode != 0:
        return int(analyze_completed.returncode)

    storyboard_args = build_storyboard_args(
        analysis=runtime_paths["analysis"],
        output=runtime_paths["storyboard"],
        brief=runtime_paths["brief"],
        extra_args=storyboard_extra_args,
    )
    storyboard_completed = run_step(storyboard_main, storyboard_args, "storyboard")
    if storyboard_completed.returncode != 0:
        return int(storyboard_completed.returncode)

    compose_args = build_compose_args(
        storyboard=runtime_paths["storyboard"],
        output_dir=args.output_dir or workspace_dir,
        extra_args=compose_extra_args,
    )
    compose_completed = run_step(compose_main, compose_args, "compose")
    if compose_completed.returncode != 0:
        return int(compose_completed.returncode)

    safe_print("[test_e2e] ✓ E2E 完成")
    safe_print(f"[test_e2e] workspace: {workspace_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())