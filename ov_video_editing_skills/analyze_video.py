from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

from .creative_brief import (
    DEFAULT_ANALYSIS_PROMPT,
    build_analysis_file_name,
    discover_creative_brief,
    derive_artifact_base_name,
    load_creative_brief,
)
from .runtime import BIN_DIR, DEFAULT_MODEL_DIR, ensure_local_requirements, maybe_reexec_in_local_venv, safe_print

cv2 = None
np = None
Image = None

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv"}
DEFAULT_PROMPT = DEFAULT_ANALYSIS_PROMPT


def load_runtime_dependencies() -> None:
    global cv2, np, Image
    if cv2 is not None and np is not None and Image is not None:
        return
    import cv2 as cv2_module
    import numpy as np_module
    from PIL import Image as image_module

    cv2 = cv2_module
    np = np_module
    Image = image_module


def discover_videos(video_dir: Path) -> list[Path]:
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
        videos = discover_videos(video_input)
        if not videos:
            raise FileNotFoundError(f"目录中未找到视频文件：{video_input}")
        return video_input, videos

    raise FileNotFoundError(f"视频目录或文件不存在：{video_input}")


def get_video_duration(video_path: Path, ffprobe_path: str | None = None) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if cap.isOpened():
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0 and frame_count > 0:
            return frame_count / fps

    if ffprobe_path and Path(ffprobe_path).exists():
        try:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass

    raise RuntimeError(f"无法获取视频时长：{video_path}")


def extract_segment_frames(
    video_path: Path,
    seg_start: float,
    seg_end: float,
    num_frames: int = 4,
    scale: float = 0.25,
):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            return []

        seg_duration = seg_end - seg_start
        if seg_duration <= 0:
            return []

        if num_frames <= 1:
            positions = [seg_start + seg_duration / 2]
        else:
            positions = [seg_start + i * seg_duration / (num_frames - 1) for i in range(num_frames)]

        frames = []
        for pos in positions:
            frame_idx = int(pos * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_frame = Image.fromarray(frame_rgb)
            if scale != 1.0 and scale > 0:
                new_w = max(1, int(pil_frame.width * scale))
                new_h = max(1, int(pil_frame.height * scale))
                pil_frame = pil_frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
            frames.append(pil_frame)
        return frames
    finally:
        cap.release()


def init_vlm_pipeline(model_dir: Path, device: str = "GPU"):
    import openvino_genai as ov_genai

    safe_print(f"[VLM] 正在初始化模型：{model_dir}")
    safe_print(f"[VLM] 设备：{device}")
    pipeline = ov_genai.VLMPipeline(str(model_dir), device)
    safe_print("[VLM] ✓ 模型初始化完成")
    return pipeline


def analyze_segment_vlm(pipeline, frames, prompt: str, max_new_tokens: int = 100) -> str:
    import openvino as ov

    frame_tensors = []
    for img in frames:
        rgb = img.convert("RGB")
        arr = np.array(rgb, dtype=np.uint8)
        frame_tensors.append(ov.Tensor(arr))

    response = pipeline.generate(
        prompt,
        videos=frame_tensors if frame_tensors else None,
        max_new_tokens=max_new_tokens,
        repetition_penalty=1.2,
    )

    result = str(response).strip() if response else ""
    for term in ["<|im_end|>", "<|endoftext|>"]:
        result = result.replace(term, "")
    result = result.strip()
    return result if result else "（模型未生成有效描述）"


def process_video(
    video_path: Path,
    pipeline,
    prompt: str,
    seg_duration: float,
    frames_per_seg: int,
    scale: float,
    max_tokens: int,
    ffprobe_path: str | None,
) -> dict[str, object]:
    duration = get_video_duration(video_path, ffprobe_path)
    num_segments = max(1, math.ceil(duration / seg_duration))
    safe_print(f"  时长：{duration:.2f}s，分 {num_segments} 段")

    segments = []
    for seg_id in range(num_segments):
        seg_start = seg_id * seg_duration
        seg_end = min((seg_id + 1) * seg_duration, duration)
        seg_dur = seg_end - seg_start
        seg_start_time = time.time()
        frames = extract_segment_frames(video_path, seg_start, seg_end, frames_per_seg, scale)

        if not frames:
            desc = "无法提取帧"
        else:
            try:
                desc = analyze_segment_vlm(pipeline, frames, prompt, max_tokens)
            except Exception as exc:
                desc = f"分析失败：{exc}"
                safe_print(f"    段 {seg_id} VLM 推理失败：{exc}", file=sys.stderr)

        elapsed = time.time() - seg_start_time
        safe_print(f"    段 {seg_id}: {seg_start:.1f}s-{seg_end:.1f}s | {len(frames)} 帧 | {elapsed:.1f}s | {desc[:50]}...")
        segments.append(
            {
                "seg_id": seg_id,
                "seg_start": round(seg_start, 3),
                "seg_end": round(seg_end, 3),
                "seg_dur": round(seg_dur, 3),
                "seg_desc": desc,
            }
        )

    return {"input_video": str(video_path), "segments": segments}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="视频分析，输出 output_vlm.json")
    parser.add_argument("--video-dir", required=True, help="视频目录或单个视频文件路径")
    parser.add_argument("--output", "--json-file", required=False, dest="output", help="输出 JSON 文件路径；未传时按视频名自动生成")
    parser.add_argument("--prompt", default=None, help="VLM 分析提示词；未传时自动读取同目录下的 brief 文件")
    parser.add_argument("--brief", default=None, help="brief JSON 路径，支持 legacy `creative_brief.json` 或 `<video_name>_brief.json`")
    parser.add_argument("--model-dir", default=None, help=f"OpenVINO 模型目录（默认：{DEFAULT_MODEL_DIR}）")
    parser.add_argument("--device", default="GPU", choices=["GPU", "CPU"], help="推理设备")
    parser.add_argument("--seg-duration", type=float, default=3.0, help="段时长秒数")
    parser.add_argument("--frames-per-seg", type=int, default=8, help="每段提取帧数")
    parser.add_argument("--scale", type=float, default=0.25, help="帧缩放比例")
    parser.add_argument("--max-tokens", type=int, default=100, help="VLM 最大生成 token 数")
    return parser.parse_args()


def resolve_prompt(explicit_prompt: str | None, search_anchor: Path, brief_arg: str | None) -> tuple[str, Path | None]:
    if explicit_prompt:
        return explicit_prompt, None

    brief_path = discover_creative_brief(Path(brief_arg).resolve() if brief_arg else None, search_anchor)
    if brief_path:
        brief = load_creative_brief(brief_path)
        return brief.analysis_prompt, brief_path
    return DEFAULT_PROMPT, None


def resolve_output_path(explicit_output: str | None, video_root: Path, videos: list[Path], brief_path: Path | None) -> Path:
    if explicit_output:
        return Path(explicit_output).resolve()

    if brief_path:
        base_name = derive_artifact_base_name(video_root, videos)
        return brief_path.parent / build_analysis_file_name(base_name)

    base_name = derive_artifact_base_name(video_root, videos)
    return video_root / build_analysis_file_name(base_name)


def main() -> int:
    args = parse_args()
    try:
        ensure_local_requirements(force=False)
        maybe_reexec_in_local_venv("ov_video_editing_skills.analyze_video")
        load_runtime_dependencies()
    except Exception as exc:
        safe_print(f"错误：运行环境检查失败：{exc}", file=sys.stderr)
        return 1

    if args.seg_duration <= 0 or args.frames_per_seg < 1 or args.scale <= 0:
        safe_print("错误：参数非法，请检查 seg-duration / frames-per-seg / scale", file=sys.stderr)
        return 1

    video_input = Path(args.video_dir).resolve()
    model_dir = Path(args.model_dir).resolve() if args.model_dir else DEFAULT_MODEL_DIR
    try:
        video_root, videos = resolve_video_input(video_input)
    except Exception as exc:
        safe_print(f"错误：{exc}", file=sys.stderr)
        return 1

    prompt, brief_path = resolve_prompt(args.prompt, Path(args.brief).resolve() if args.brief else video_input, args.brief)
    output_path = resolve_output_path(args.output, video_root, videos, brief_path)
    ffprobe_name = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
    ffprobe_path = str(BIN_DIR / ffprobe_name)

    if not model_dir.is_dir():
        safe_print(f"错误：模型目录不存在：{model_dir}", file=sys.stderr)
        safe_print("请先按 README 中的说明手动放置模型目录。", file=sys.stderr)
        return 1

    safe_print(f"[分析] 找到 {len(videos)} 个视频文件")
    safe_print(f"[分析] 输入根目录：{video_root}")
    safe_print(f"[分析] 模型：{model_dir}")
    safe_print(f"[分析] 设备：{args.device}")
    if brief_path:
        safe_print(f"[分析] 使用 brief：{brief_path}")
    safe_print(f"[分析] 输出文件：{output_path}")
    safe_print(f"[分析] 段时长：{args.seg_duration}s，每段 {args.frames_per_seg} 帧，缩放 {args.scale}")

    total_start = time.time()
    pipeline = init_vlm_pipeline(model_dir, args.device)

    results = []
    for index, video_path in enumerate(videos, start=1):
        pct = int(((index - 1) / len(videos)) * 100)
        safe_print(f"\n[{index}/{len(videos)}] {pct}% {video_path.name}")
        results.append(
            process_video(
                video_path=video_path,
                pipeline=pipeline,
                prompt=prompt,
                seg_duration=args.seg_duration,
                frames_per_seg=args.frames_per_seg,
                scale=args.scale,
                max_tokens=args.max_tokens,
                ffprobe_path=ffprobe_path,
            )
        )

    output_data = {
        "analysis_prompt": prompt,
        "brief_path": str(brief_path) if brief_path else "",
        "processed_videos": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file_obj:
        json.dump(output_data, file_obj, ensure_ascii=False, indent=2)

    total_time = time.time() - total_start
    total_segments = sum(len(item["segments"]) for item in results)
    safe_print(f"\n[分析] ✓ 完成：{len(videos)} 个视频，{total_segments} 个段，总耗时 {total_time:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
