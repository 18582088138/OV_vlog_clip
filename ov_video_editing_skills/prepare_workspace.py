from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .bootstrap import bootstrap_environment
from .creative_brief import (
    build_analysis_file_name,
    build_brief_file_name,
    create_creative_brief,
    derive_artifact_base_name,
    save_creative_brief,
)
from .runtime import safe_print, write_runtime_manifest

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv"}
ANALYSIS_FILE_NAME = "output_vlm.json"


def find_videos(video_dir: Path) -> list[Path]:
    videos: list[Path] = []
    for file_path in sorted(video_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(file_path)
    return videos


def resolve_video_input(video_input: Path) -> tuple[Path, list[Path]]:
    if video_input.is_file():
        if video_input.suffix.lower() not in VIDEO_EXTENSIONS:
            raise FileNotFoundError(f"不支持的视频文件格式：{video_input}")
        return video_input.parent, [video_input]

    if video_input.is_dir():
        videos = find_videos(video_input)
        if not videos:
            raise FileNotFoundError(f"目录中未找到视频文件：{video_input}")
        return video_input, videos

    raise FileNotFoundError(f"视频目录或文件不存在：{video_input}")


def summarize_analysis_output(analysis_path: Path) -> dict[str, int]:
    try:
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"无法读取已有分析结果：{analysis_path} ({exc})") from exc

    processed_videos = payload.get("processed_videos")
    if not isinstance(processed_videos, list) or not processed_videos:
        raise ValueError(f"已有分析结果缺少有效的 processed_videos：{analysis_path}")

    segment_count = 0
    valid_video_count = 0
    for video in processed_videos:
        segments = video.get("segments") or []
        if not isinstance(segments, list):
            continue
        if segments:
            valid_video_count += 1
            segment_count += len(segments)

    if segment_count <= 0:
        raise ValueError(f"已有分析结果中未找到可用 segments：{analysis_path}")

    return {
        "processed_video_count": valid_video_count,
        "segment_count": segment_count,
    }


def stage_existing_analysis(
    video_dir: Path,
    workspace: Path,
    artifact_base_name: str,
    ignore_existing_analysis: bool = False,
) -> dict[str, object]:
    candidate_names = [build_analysis_file_name(artifact_base_name), ANALYSIS_FILE_NAME]
    analysis_source = next((video_dir / name for name in candidate_names if (video_dir / name).exists()), video_dir / candidate_names[0])
    analysis_target = workspace / build_analysis_file_name(artifact_base_name)

    if not analysis_source.exists():
        return {
            "analysis_mode": "fresh_analysis_required",
            "analysis_source": "",
            "workspace_analysis": str(analysis_target),
            "analysis_processed_video_count": 0,
            "analysis_segment_count": 0,
        }

    if ignore_existing_analysis:
        return {
            "analysis_mode": "ignore_existing_output",
            "analysis_source": str(analysis_source),
            "workspace_analysis": str(analysis_target),
            "analysis_processed_video_count": 0,
            "analysis_segment_count": 0,
        }

    summary = summarize_analysis_output(analysis_source)
    shutil.copy2(analysis_source, analysis_target)
    return {
        "analysis_mode": "reuse_existing_output",
        "analysis_source": str(analysis_source),
        "workspace_analysis": str(analysis_target),
        "analysis_processed_video_count": summary["processed_video_count"],
        "analysis_segment_count": summary["segment_count"],
    }


def prepare_workspace(
    video_dir: Path,
    user_request: str | None = None,
    force_requirements: bool = False,
    force_ffmpeg: bool = False,
    force_model: bool = False,
    skip_ffmpeg: bool = False,
    skip_model: bool = False,
    ignore_existing_analysis: bool = False,
) -> tuple[Path, dict[str, str], dict[str, object]]:
    workspace_root, videos = resolve_video_input(video_dir)
    artifact_base_name = derive_artifact_base_name(workspace_root, videos)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace = workspace_root / f"editing_{timestamp}"
    workspace.mkdir(parents=True, exist_ok=True)

    if user_request:
        (workspace / "user_input.txt").write_text(user_request, encoding="utf-8")

    brief = create_creative_brief(user_request)
    brief_path = save_creative_brief(workspace, brief, build_brief_file_name(artifact_base_name))
    analysis_info = stage_existing_analysis(
        video_dir=workspace_root,
        workspace=workspace,
        artifact_base_name=artifact_base_name,
        ignore_existing_analysis=ignore_existing_analysis,
    )

    runtime = bootstrap_environment(
        force_requirements=force_requirements,
        force_ffmpeg=force_ffmpeg,
        force_model=force_model,
        skip_ffmpeg=skip_ffmpeg,
        skip_model=skip_model,
    )

    write_runtime_manifest(
        workspace,
        extra={
            "video_dir": str(video_dir),
            "workspace_root": str(workspace_root),
            "artifact_base_name": artifact_base_name,
            "video_count": len(videos),
            "videos": [str(path) for path in videos],
            "creative_brief": str(brief_path),
            **analysis_info,
        },
    )
    return workspace, runtime, analysis_info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证视频目录、创建工作区并完成运行时准备")
    parser.add_argument("--video-dir", required=True, help="视频文件所在目录")
    parser.add_argument("--user-request", default=None, help="用户原始请求")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="跳过 ffmpeg / ffprobe 检查")
    parser.add_argument("--skip-model", action="store_true", help="跳过模型准备")
    parser.add_argument("--force-requirements", action="store_true", help="强制重新安装 requirements.txt")
    parser.add_argument("--force-ffmpeg", action="store_true", help="强制重新下载 ffmpeg / ffprobe")
    parser.add_argument("--force-model", action="store_true", help="强制重新下载模型")
    parser.add_argument("--ignore-existing-analysis", action="store_true", help="忽略视频目录下已有的 output_vlm.json，后续阶段重新分析")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_dir = Path(args.video_dir).resolve()
    brief_output_path = ""

    try:
        workspace_root, videos = resolve_video_input(video_dir)
        artifact_base_name = derive_artifact_base_name(workspace_root, videos)
        brief_output_path = str(Path(workspace_root) / build_brief_file_name(artifact_base_name))
        safe_print(f"[准备] 找到 {len(videos)} 个视频文件：")
        for video in videos:
            safe_print(f"  {video.name}")

        workspace, runtime, analysis_info = prepare_workspace(
            video_dir=video_dir,
            user_request=args.user_request,
            force_requirements=args.force_requirements,
            force_ffmpeg=args.force_ffmpeg,
            force_model=args.force_model,
            skip_ffmpeg=args.skip_ffmpeg,
            skip_model=args.skip_model,
            ignore_existing_analysis=args.ignore_existing_analysis,
        )
    except Exception as exc:
        safe_print(f"[准备] ✗ 失败：{exc}", file=sys.stderr)
        return 1

    safe_print(f"[准备] 工作区已创建：{workspace}")
    safe_print(f"[准备] 素材根目录：{workspace_root}")
    runtime_manifest = workspace / "runtime_env.json"
    if runtime_manifest.exists():
        try:
            runtime_payload = json.loads(runtime_manifest.read_text(encoding="utf-8"))
            brief_output_path = str(runtime_payload.get("creative_brief") or brief_output_path)
        except Exception:
            pass
    safe_print(f"[准备] brief 已生成：{brief_output_path}")
    if analysis_info["analysis_mode"] == "reuse_existing_output":
        safe_print(f"[准备] 复用已有分析结果：{analysis_info['analysis_source']} -> {analysis_info['workspace_analysis']}")
    elif analysis_info["analysis_mode"] == "ignore_existing_output":
        safe_print(f"[准备] 已忽略现有分析结果：{analysis_info['analysis_source']}")
    else:
        safe_print(f"[准备] 未发现可复用分析结果，后续请输出到：{analysis_info['workspace_analysis']}")
    safe_print("[准备] ✓ 运行时准备完成")
    safe_print(json.dumps(runtime, ensure_ascii=False, indent=2))
    safe_print(str(workspace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
