from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runtime import BIN_DIR, DEFAULT_MODEL_DIR, ensure_local_requirements, runtime_summary, safe_print


def ffmpeg_paths() -> tuple[Path, Path]:
    ffmpeg_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    ffprobe_name = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
    return BIN_DIR / ffmpeg_name, BIN_DIR / ffprobe_name


def ensure_ffmpeg(force: bool = False) -> None:
    del force
    ffmpeg_path, ffprobe_path = ffmpeg_paths()
    missing = [str(path) for path in (ffmpeg_path, ffprobe_path) if not path.exists()]
    if missing:
        raise RuntimeError("缺少 ffmpeg / ffprobe，请手动下载后放入 bin 目录：" + "；".join(missing))
    safe_print(f"[bootstrap] 已检测到 ffmpeg：{ffmpeg_path}")
    safe_print(f"[bootstrap] 已检测到 ffprobe：{ffprobe_path}")


def ensure_model(force: bool = False) -> None:
    del force
    if not DEFAULT_MODEL_DIR.exists():
        raise RuntimeError(f"缺少模型目录，请手动下载并放置到：{DEFAULT_MODEL_DIR}")
    safe_print(f"[bootstrap] 已检测到模型目录：{DEFAULT_MODEL_DIR}")


def bootstrap_environment(
    force_requirements: bool = False,
    force_ffmpeg: bool = False,
    force_model: bool = False,
    skip_ffmpeg: bool = False,
    skip_model: bool = False,
) -> dict[str, str]:
    ensure_local_requirements(force=force_requirements)
    if not skip_ffmpeg:
        ensure_ffmpeg(force=force_ffmpeg)
    if not skip_model:
        ensure_model(force=force_model)
    return runtime_summary()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一检查：当前 Python 环境、ffmpeg、模型")
    parser.add_argument("--force-requirements", action="store_true", help="保留兼容参数；当前不会自动安装依赖")
    parser.add_argument("--force-ffmpeg", action="store_true", help="保留兼容参数；当前不会自动下载 ffmpeg / ffprobe")
    parser.add_argument("--force-model", action="store_true", help="保留兼容参数；当前不会自动下载模型")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="跳过 ffmpeg / ffprobe 检查")
    parser.add_argument("--skip-model", action="store_true", help="跳过模型检查")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = bootstrap_environment(
            force_requirements=args.force_requirements,
            force_ffmpeg=args.force_ffmpeg,
            force_model=args.force_model,
            skip_ffmpeg=args.skip_ffmpeg,
            skip_model=args.skip_model,
        )
    except Exception as exc:
        print(f"[bootstrap] ✗ 失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        safe_print("[bootstrap] ✓ 环境检查完成")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
