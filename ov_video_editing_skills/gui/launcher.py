from __future__ import annotations

import argparse
import importlib
import sys

from ..runtime import safe_print


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ov-video-editing-gui", description="启动 ov-video-editing-skills 桌面 GUI")
    parser.add_argument("--settings", default=None, help="GUI 配置文件路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        module = importlib.import_module("ov_video_editing_skills.gui.qt_app")
    except ModuleNotFoundError as exc:
        missing_name = exc.name or ""
        if missing_name.startswith("PySide6") or "PySide6" in str(exc):
            safe_print("[gui] 未安装 PySide6，请先安装 GUI 依赖：python -m pip install -r requirements-gui.txt", file=sys.stderr)
            return 1
        raise

    return int(module.run_gui(settings_path=args.settings))