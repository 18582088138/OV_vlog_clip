from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .runtime import BIN_DIR, PROJECT_DIR, ensure_local_venv, maybe_reexec_in_local_venv, min_python_display, safe_print

FFMPEG_ZIP_URL = "https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/ffmpeg-8.0.1-full_build.zip"


def ffmpeg_binary_name() -> str:
    return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def ffprobe_binary_name() -> str:
    return "ffprobe.exe" if os.name == "nt" else "ffprobe"


def inspect_ffmpeg() -> dict[str, object]:
    ffmpeg_dest = BIN_DIR / ffmpeg_binary_name()
    ffprobe_dest = BIN_DIR / ffprobe_binary_name()

    return {
        "ffmpeg_path": str(ffmpeg_dest),
        "ffprobe_path": str(ffprobe_dest),
        "ffmpeg_exists": ffmpeg_dest.exists(),
        "ffprobe_exists": ffprobe_dest.exists(),
        "ready": ffmpeg_dest.exists() and ffprobe_dest.exists(),
        "download_url": FFMPEG_ZIP_URL,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 ffmpeg / ffprobe 是否已手动放入本地 bin 目录")
    return parser.parse_args()


def _check_python_version() -> None:
    major, minor = sys.version_info[:2]
    ver_str = f"{major}.{minor}.{sys.version_info.micro}"
    if major > 3 or (major == 3 and minor >= 10):
        safe_print(f"[python] ✓ Python {ver_str}（满足 >= {min_python_display()} 要求）")
    else:
        safe_print(f"[python] ⚠ 当前 Python 版本：{ver_str}，需要 Python >= {min_python_display()}", file=sys.stderr)


def main() -> int:
    _ = parse_args()
    ensure_local_venv()
    maybe_reexec_in_local_venv("ov_video_editing_skills.setup_resources")

    safe_print("=" * 60)
    safe_print("ov-video-editing-skills 资源检查脚本")
    safe_print(f"PROJECT_DIR : {PROJECT_DIR}")
    safe_print(f"BIN_DIR     : {BIN_DIR}")
    safe_print("=" * 60)
    _check_python_version()

    report = inspect_ffmpeg()
    safe_print("\n[1/1] ffmpeg / ffprobe")
    if report["ready"]:
        safe_print(f"[ffmpeg] ✓ 已检测到：{report['ffmpeg_path']}")
        safe_print(f"[ffmpeg] ✓ 已检测到：{report['ffprobe_path']}")
        safe_print("\n✓ 资源检查通过。")
        return 0

    safe_print("[ffmpeg] ✗ 未检测到完整二进制，请手动下载并放置到：", file=sys.stderr)
    safe_print(f"  - {report['ffmpeg_path']}", file=sys.stderr)
    safe_print(f"  - {report['ffprobe_path']}", file=sys.stderr)
    safe_print(f"[ffmpeg] 下载地址：{report['download_url']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
