from __future__ import annotations

import argparse
import sys

from . import __version__
from .analyze_video import main as analyze_main
from .bootstrap import main as bootstrap_main
from .compose_video import main as compose_main
from .e2e import main as e2e_main
from .generate_storyboard import main as storyboard_main
from .prepare_workspace import main as prepare_main
from .setup_ov_model import main as model_main
from .setup_resources import main as resources_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ov-video-editing-skills",
        description="本地纯 Python vlog 视频分析 / 分镜 / 合成工具",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("bootstrap", help="准备本地 .venv、ffmpeg 和模型")
    subparsers.add_parser("setup-resources", help="下载 ffmpeg / ffprobe")
    subparsers.add_parser("setup-model", help="下载 OpenVINO VLM 模型")
    subparsers.add_parser("prepare", help="检查视频目录并创建工作区")
    subparsers.add_parser("analyze", help="分析视频并输出 output_vlm.json")
    subparsers.add_parser("storyboard", help="从 output_vlm.json 生成 storyboard.json")
    subparsers.add_parser("compose", help="根据 storyboard.json 合成最终视频")
    subparsers.add_parser("e2e", help="串联执行 prepare/analyze/storyboard/compose")
    subparsers.add_parser("gui", help="启动桌面 GUI")
    return parser


def run_subcommand(handler, argv: list[str]) -> int:
    original_argv = sys.argv[:]
    try:
        sys.argv = [original_argv[0], *argv]
        return handler()
    finally:
        sys.argv = original_argv


def main() -> int:
    parser = build_parser()
    args, remaining = parser.parse_known_args()

    if args.command == "bootstrap":
        return run_subcommand(bootstrap_main, remaining)
    if args.command == "setup-resources":
        return run_subcommand(resources_main, remaining)
    if args.command == "setup-model":
        return run_subcommand(model_main, remaining)
    if args.command == "prepare":
        return run_subcommand(prepare_main, remaining)
    if args.command == "analyze":
        return run_subcommand(analyze_main, remaining)
    if args.command == "storyboard":
        return run_subcommand(storyboard_main, remaining)
    if args.command == "compose":
        return run_subcommand(compose_main, remaining)
    if args.command == "e2e":
        return run_subcommand(e2e_main, remaining)
    if args.command == "gui":
        from .gui.launcher import main as gui_main

        return gui_main(remaining)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
