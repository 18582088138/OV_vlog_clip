from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_STORYBOARD_CANDIDATES = (
    "videos",
    "videos/2022yunqidahui_storyboard.json",
    "videos/storyboard.json",
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_storyboard_input(repo_root: Path) -> Path:
    for candidate in DEFAULT_STORYBOARD_CANDIDATES:
        resolved = repo_root / candidate
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        "未找到默认 storyboard 输入，请通过 --storyboard 显式传入 storyboard 文件或工作目录。"
    )


def build_compose_command(
    repo_root: Path,
    python_executable: str | Path,
    storyboard: str | Path | None = None,
    output_dir: str | Path | None = None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    target = Path(storyboard).resolve() if storyboard else default_storyboard_input(repo_root)
    command = [
        str(python_executable),
        "run.py",
        "compose",
        "--storyboard",
        str(target),
    ]
    if output_dir:
        command.extend(["--output-dir", str(Path(output_dir).resolve())])
    if extra_args:
        command.extend(extra_args)
    return command


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="测试 `compose` 命令的辅助脚本")
    parser.add_argument("--storyboard", default=None, help="storyboard JSON 文件或工作目录；未传时自动尝试仓库内默认位置")
    parser.add_argument("--output-dir", default=None, help="可选输出目录；未传时使用 storyboard 所在目录")
    parser.add_argument("--python", dest="python_executable", default=sys.executable, help="执行命令使用的 Python 解释器")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不实际执行")
    return parser.parse_known_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_args = parse_args(argv)
    repo_root = project_root()
    command = build_compose_command(
        repo_root=repo_root,
        python_executable=args.python_executable,
        storyboard=args.storyboard,
        output_dir=args.output_dir,
        extra_args=extra_args,
    )

    print("[test_compose] repo:", repo_root)
    print("[test_compose] command:", subprocess.list2cmdline(command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, cwd=repo_root)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())