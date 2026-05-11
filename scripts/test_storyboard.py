from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_ANALYSIS_CANDIDATES = (
    "videos",
    "videos/2022yunqidahui_output_vlm.json",
    "videos/output_vlm.json",
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_analysis_input(repo_root: Path) -> Path:
    for candidate in DEFAULT_ANALYSIS_CANDIDATES:
        resolved = repo_root / candidate
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        "未找到默认分析输入，请通过 --analysis 显式传入分析结果文件或工作目录。"
    )


def build_storyboard_command(
    repo_root: Path,
    python_executable: str | Path,
    analysis: str | Path | None = None,
    output: str | Path | None = None,
    brief: str | Path | None = None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    target = Path(analysis).resolve() if analysis else default_analysis_input(repo_root)
    command = [
        str(python_executable),
        "run.py",
        "storyboard",
        "--analysis",
        str(target),
    ]
    if output:
        command.extend(["--output", str(Path(output).resolve())])
    if brief:
        command.extend(["--brief", str(Path(brief).resolve())])
    if extra_args:
        command.extend(extra_args)
    return command


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="测试 `storyboard` 命令的辅助脚本")
    parser.add_argument("--analysis", default=None, help="分析结果 JSON 文件或工作目录；未传时自动尝试仓库内默认位置")
    parser.add_argument("--output", default=None, help="可选 storyboard 输出路径；未传时由 storyboard 自动命名")
    parser.add_argument("--brief", default=None, help="可选 brief 文件路径；未传时由 storyboard 自动发现")
    parser.add_argument("--python", dest="python_executable", default=sys.executable, help="执行命令使用的 Python 解释器")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不实际执行")
    return parser.parse_known_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_args = parse_args(argv)
    repo_root = project_root()
    command = build_storyboard_command(
        repo_root=repo_root,
        python_executable=args.python_executable,
        analysis=args.analysis,
        output=args.output,
        brief=args.brief,
        extra_args=extra_args,
    )

    print("[test_storyboard] repo:", repo_root)
    print("[test_storyboard] command:", subprocess.list2cmdline(command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, cwd=repo_root)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())