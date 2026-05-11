from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ov_video_editing_skills.creative_brief import (
    build_analysis_file_name,
    build_brief_file_name,
    build_storyboard_file_name,
    derive_artifact_base_name,
)
from ov_video_editing_skills.runtime import safe_print

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


def run_step(command: list[str], repo_root: Path, label: str) -> subprocess.CompletedProcess[str]:
    safe_print(f"[test_e2e] running {label}: {subprocess.list2cmdline(command)}")
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    completed = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if completed.stdout:
        safe_print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        safe_print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return completed


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
    parser.add_argument("--python", dest="python_executable", default=sys.executable, help="执行命令使用的 Python 解释器")
    parser.add_argument("--ignore-existing-analysis", action="store_true", help="透传给 prepare，忽略已有分析结果")
    parser.add_argument("--dry-run", action="store_true", help="只打印完整 E2E 命令链，不实际执行")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = project_root()
    commands = build_e2e_commands(
        repo_root=repo_root,
        python_executable=args.python_executable,
        video_dir=args.video_dir,
        user_request=args.user_request,
        ignore_existing_analysis=args.ignore_existing_analysis,
        output_dir=args.output_dir,
    )

    safe_print("[test_e2e] repo:", repo_root)
    safe_print("[test_e2e] artifact paths:", json.dumps(commands["paths"], ensure_ascii=False, indent=2))
    for label in ("prepare", "analyze", "storyboard", "compose"):
        safe_print(f"[test_e2e] {label}: {subprocess.list2cmdline(commands[label])}")

    if args.dry_run:
        return 0

    prepare_completed = run_step(commands["prepare"], repo_root, "prepare")
    if prepare_completed.returncode != 0:
        return int(prepare_completed.returncode)

    workspace_dir = extract_workspace_from_prepare_output(prepare_completed.stdout, prepare_completed.stderr)
    runtime_paths = load_runtime_paths(workspace_dir, args.video_dir)
    runtime_commands = build_e2e_commands(
        repo_root=repo_root,
        python_executable=args.python_executable,
        video_dir=args.video_dir,
        user_request=args.user_request,
        ignore_existing_analysis=args.ignore_existing_analysis,
        output_dir=args.output_dir or workspace_dir,
        workspace_dir=workspace_dir,
    )
    runtime_commands["paths"] = runtime_paths
    runtime_commands["analyze"] = build_analyze_command(
        repo_root=repo_root,
        python_executable=args.python_executable,
        video_dir=args.video_dir,
        brief=runtime_paths["brief"],
        output=runtime_paths["analysis"],
    )
    runtime_commands["storyboard"] = build_storyboard_command(
        python_executable=args.python_executable,
        analysis=runtime_paths["analysis"],
        output=runtime_paths["storyboard"],
        brief=runtime_paths["brief"],
    )
    runtime_commands["compose"] = build_compose_command(
        python_executable=args.python_executable,
        storyboard=runtime_paths["storyboard"],
        output_dir=args.output_dir or workspace_dir,
    )

    for label in ("analyze", "storyboard", "compose"):
        completed = run_step(runtime_commands[label], repo_root, label)
        if completed.returncode != 0:
            return int(completed.returncode)

    safe_print("[test_e2e] ✓ E2E 完成")
    safe_print(f"[test_e2e] workspace: {workspace_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
