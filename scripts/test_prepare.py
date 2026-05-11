from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_REQUEST = "做一个30秒的视频总结vlog"
DEFAULT_VIDEO_CANDIDATES = (
    "videos/2022yunqidahui.mp4",
    "videos",
)


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


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="测试 `prepare` 命令的辅助脚本")
    parser.add_argument("--video-dir", default=None, help="视频目录或单个视频文件；未传时自动尝试仓库内默认素材")
    parser.add_argument("--user-request", default=DEFAULT_REQUEST, help="传给 prepare 的用户需求描述")
    parser.add_argument("--python", dest="python_executable", default=sys.executable, help="执行命令使用的 Python 解释器")
    parser.add_argument("--ignore-existing-analysis", action="store_true", help="透传给 prepare，忽略已存在分析结果")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不实际执行")
    return parser.parse_known_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_args = parse_args(argv)
    repo_root = project_root()
    command = build_prepare_command(
        repo_root=repo_root,
        python_executable=args.python_executable,
        video_dir=args.video_dir,
        user_request=args.user_request,
        ignore_existing_analysis=args.ignore_existing_analysis,
        extra_args=extra_args,
    )

    print("[test_prepare] repo:", repo_root)
    print("[test_prepare] command:", subprocess.list2cmdline(command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, cwd=repo_root)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
