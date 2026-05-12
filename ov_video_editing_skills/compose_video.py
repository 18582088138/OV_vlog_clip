from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .creative_brief import LEGACY_STORYBOARD_FILE_NAME, STORYBOARD_FILE_SUFFIX
from .runtime import BGM_DIR, BIN_DIR, ensure_local_requirements, hidden_subprocess_kwargs, maybe_reexec_in_local_venv, safe_print

VALID_XFADE_TRANSITIONS = {
    "fade", "dissolve", "fadeblack", "fadewhite",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose",
}
DEFAULT_SUBTITLE_FONT_SIZE = 15
DEFAULT_SUBTITLE_MAX_LINE_LEN = 100
DEFAULT_BGM_VOLUME = 0.85
DEFAULT_SUBTITLE_FONT_NAME = "Microsoft YaHei"

PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "：": ":",
        "；": ";",
        "！": "!",
        "？": "?",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "《": "<",
        "》": ">",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "、": ",",
        "—": "-",
        "…": "...",
    }
)


@dataclass
class ClipSpec:
    clip_id: int
    sequence_order: int
    source_video: Path
    in_point: float
    out_point: float
    duration: float
    subtitle: str
    transition: str = ""
    transition_duration: float = 0.8


@dataclass
class StoryboardMeta:
    theme: str
    target_duration: Optional[float]
    actual_duration: Optional[float]


def coerce_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sanitize_filename_component(value: str, fallback: str, max_len: int = 48) -> str:
    safe = str(value or "").strip() or fallback
    safe = re.sub(r'[<>:"/\\|?*]', "_", safe)
    safe = re.sub(r"\s+", "_", safe).strip("._ ")
    if not safe:
        safe = fallback
    return safe[:max_len]


def format_duration_component(target: Optional[float], actual: Optional[float], clips: List[ClipSpec]) -> str:
    duration = target or actual
    if duration is None:
        duration = sum(clip.duration for clip in clips)
    if not duration or duration <= 0:
        return "unknown"
    return f"{int(round(duration))}s"


def resolve_storyboard_bgm_path(raw_value: str, storyboard_path: Path) -> Optional[Path]:
    if not raw_value:
        return None
    candidate = Path(str(raw_value))
    if candidate.is_absolute():
        return candidate
    relative_candidate = (storyboard_path.parent / candidate).resolve()
    if relative_candidate.exists():
        return relative_candidate
    fallback_candidate = BGM_DIR / candidate.name
    if fallback_candidate.exists():
        return fallback_candidate
    return relative_candidate


def load_storyboard(path: Path) -> Tuple[List[ClipSpec], Optional[Path], StoryboardMeta]:
    if not path.exists():
        raise FileNotFoundError(f"Storyboard not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    storyboard_metadata = data.get("storyboard_metadata") or {}
    story_outline = data.get("story_outline") or {}
    theme_value = storyboard_metadata.get("theme") or story_outline.get("title") or "video"
    meta = StoryboardMeta(
        theme=str(theme_value).strip() or "video",
        target_duration=coerce_float(storyboard_metadata.get("target_duration_seconds")),
        actual_duration=coerce_float(storyboard_metadata.get("actual_duration_seconds")),
    )

    audio_design = data.get("audio_design") or {}
    background_music = audio_design.get("background_music") or {}
    bgm_value = background_music.get("file_path") or background_music.get("bgm_file") or background_music.get("selected_bgm")
    bgm_path = resolve_storyboard_bgm_path(str(bgm_value), path) if bgm_value else None

    clips = data.get("clips", [])
    if not clips:
        raise ValueError("Storyboard has no 'clips' entries.")

    specs: List[ClipSpec] = []
    for idx, clip in enumerate(clips, start=1):
        timecode = clip.get("timecode", {})
        in_point = float(timecode.get("in_point", 0.0))
        out_point = float(timecode.get("out_point", 0.0))
        duration = timecode.get("duration")
        if duration is None:
            duration = max(0.0, out_point - in_point)
        duration = float(duration)
        if out_point <= in_point or duration <= 0:
            raise ValueError(f"Invalid timecode for clip_id={clip.get('clip_id')}")

        subtitle = str((clip.get("voiceover") or {}).get("text", "")).strip()
        source_path = Path(clip["source_video"])
        if not source_path.exists():
            raise FileNotFoundError(f"clip {idx} 的 source_video 文件不存在：{source_path}")

        trans_obj = clip.get("transition") or {}
        trans_type = str(trans_obj.get("type", "")).strip().lower()
        trans_dur = float(trans_obj.get("duration", 0.8))
        if trans_type and trans_type not in VALID_XFADE_TRANSITIONS:
            safe_print(f"Warning: clip {idx} transition '{trans_type}' not supported, ignoring.")
            trans_type = ""

        specs.append(
            ClipSpec(
                clip_id=int(clip.get("clip_id", idx)),
                sequence_order=int(clip.get("sequence_order", idx)),
                source_video=source_path,
                in_point=in_point,
                out_point=out_point,
                duration=duration,
                subtitle=subtitle,
                transition=trans_type,
                transition_duration=trans_dur,
            )
        )

    return sorted(specs, key=lambda clip: clip.sequence_order), bgm_path, meta


def wrap_text(text: str, max_len: int) -> str:
    if not text or "\n" in text:
        return text
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_len:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return "\n".join(lines)


def resolve_subtitle_style(subtitle_text: str, font_size: int, max_line_len: int) -> tuple[int, int]:
    normalized_text = str(subtitle_text or "").strip()
    adjusted_line_len = max(10, min(max_line_len, DEFAULT_SUBTITLE_MAX_LINE_LEN))
    adjusted_font_size = font_size

    if len(normalized_text) >= adjusted_line_len * 3:
        adjusted_font_size = int(font_size * 0.68)
    elif len(normalized_text) >= adjusted_line_len * 2:
        adjusted_font_size = int(font_size * 0.78)
    elif len(normalized_text) >= adjusted_line_len:
        adjusted_font_size = int(font_size * 0.88)

    adjusted_font_size = max(10, adjusted_font_size)
    return adjusted_font_size, adjusted_line_len


def normalize_subtitle_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(char for char in normalized if char == "\n" or char >= " ")
    normalized = normalized.translate(PUNCTUATION_TRANSLATION)
    return normalized.strip()


def infer_font_name(font_file: Optional[Path]) -> str:
    if not font_file:
        return DEFAULT_SUBTITLE_FONT_NAME
    stem = font_file.stem.lower()
    if "msyh" in stem or "yahei" in stem:
        return "Microsoft YaHei"
    if "simhei" in stem:
        return "SimHei"
    if "simsun" in stem:
        return "SimSun"
    return DEFAULT_SUBTITLE_FONT_NAME


def escape_ass_text(value: str) -> str:
    value = normalize_subtitle_text(value)
    value = value.replace("\\", r"\\")
    value = value.replace("{", "（").replace("}", "）")
    value = value.replace("\n", r"\N")
    return value


def build_ass_subtitle_content(subtitle_text: str, font_name: str, font_size: int) -> str:
    escaped_text = escape_ass_text(subtitle_text)
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00303030,&H66000000,0,0,0,0,100,100,0,0,3,2,0,2,60,60,42,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            f"Dialogue: 0,0:00:00.00,9:59:59.00,Default,,0,0,0,,{escaped_text}",
        ]
    )


def write_ass_subtitle_file(output_path: Path, subtitle_text: str, font_name: str, font_size: int) -> Path:
    subtitle_path = output_path.with_suffix(".ass")
    subtitle_path.write_text(
        build_ass_subtitle_content(subtitle_text, font_name, font_size),
        encoding="utf-8-sig",
    )
    return subtitle_path


def build_subtitles_filter(subtitle_path: Path, font_file: Optional[Path]) -> str:
    filter_value = f"subtitles='{escape_drawtext_path(str(normalize_filter_path(subtitle_path)))}'"
    if font_file:
        filter_value += f":fontsdir='{escape_drawtext_path(str(font_file.parent))}'"
    return filter_value


def escape_drawtext_text(value: str) -> str:
    value = value.replace("\\", r"\\")
    value = value.replace(":", r"\:")
    value = value.replace(",", r"\,")
    value = value.replace("'", r"\'")
    value = value.replace("\n", r"\n")
    return value


def escape_drawtext_path(value: str) -> str:
    value = value.replace("\\", "/")
    return value.replace(":", "\\\\:")


def quote_concat_path(path: Path) -> str:
    safe = str(path).replace("\\", "/").replace('"', r'\"')
    return f'file "{safe}"'


def find_default_font() -> Optional[Path]:
    for candidate in [Path(r"C:\Windows\Fonts\msyh.ttc"), Path(r"C:\Windows\Fonts\simhei.ttf"), Path(r"C:\Windows\Fonts\simsun.ttc")]:
        if candidate.exists():
            safe_print(f"Info: Using system font: {candidate}")
            return candidate
    return None


def normalize_filter_path(path: Path) -> Path:
    if not path.is_absolute():
        return path
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        try:
            rel = Path(os.path.relpath(path, Path.cwd()))
            if ":" not in rel.as_posix():
                return rel
        except Exception:
            pass
    return path


def run_cmd(cmd: List[str], dry_run: bool) -> None:
    safe_print(" ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, capture_output=True, text=True, **hidden_subprocess_kwargs())
    if result.returncode != 0:
        raise RuntimeError("Command failed:\n" + " ".join(cmd) + "\n\n" + (result.stderr or result.stdout or ""))


def _is_valid_clip(ffmpeg: str, output_path: Path) -> bool:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False
    ffprobe = Path(ffmpeg).with_name("ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
    probe_bin = str(ffprobe) if ffprobe.exists() else "ffprobe"
    result = subprocess.run(
        [probe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True,
        text=True,
        **hidden_subprocess_kwargs(),
    )
    value = result.stdout.strip()
    return bool(value) and value.lower() not in ("n/a", "")


def extract_clip(ffmpeg: str, source_video: Path, output_path: Path, in_point: float, duration: float, dry_run: bool) -> None:
    cmd_input_seek = [ffmpeg, "-y", "-ss", f"{in_point}", "-i", str(source_video), "-t", f"{duration}", "-c", "copy", "-avoid_negative_ts", "make_zero", str(output_path)]
    cmd_output_seek = [ffmpeg, "-y", "-i", str(source_video), "-ss", f"{in_point}", "-t", f"{duration}", "-c", "copy", "-avoid_negative_ts", "make_zero", str(output_path)]

    if dry_run:
        safe_print(" ".join(cmd_input_seek))
        return

    safe_print(" ".join(cmd_input_seek))
    result = subprocess.run(cmd_input_seek, capture_output=True, text=True, **hidden_subprocess_kwargs())
    if result.returncode == 0 and _is_valid_clip(ffmpeg, output_path):
        return

    safe_print("[extract_clip] 输入侧 seek 失败或输出无效，切换到输出侧 seek 模式重试...")
    safe_print(" ".join(cmd_output_seek))
    result2 = subprocess.run(cmd_output_seek, capture_output=True, text=True, **hidden_subprocess_kwargs())
    if result2.returncode != 0 or not _is_valid_clip(ffmpeg, output_path):
        raise RuntimeError("Command failed (both seek modes):\n" + " ".join(cmd_output_seek) + "\n\n" + (result2.stderr or result2.stdout or ""))


def find_default_ffmpeg() -> str:
    exe_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    candidate = BIN_DIR / exe_name
    return str(candidate) if candidate.exists() else "ffmpeg"


def resolve_ffprobe(ffmpeg: str) -> str:
    ffmpeg_path = Path(ffmpeg)
    probe_name = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
    if ffmpeg_path.exists():
        candidate = ffmpeg_path.with_name(probe_name)
        if candidate.exists():
            return str(candidate)
    return "ffprobe"


def parse_duration_from_ffmpeg_output(output: str) -> Optional[float]:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def get_media_duration(ffprobe: str, ffmpeg: str, media_path: Path) -> Optional[float]:
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(media_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, **hidden_subprocess_kwargs())
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    result = subprocess.run([ffmpeg, "-i", str(media_path)], capture_output=True, text=True, **hidden_subprocess_kwargs())
    return parse_duration_from_ffmpeg_output(result.stderr or result.stdout)


def has_audio_stream(ffprobe: str, ffmpeg: str, media_path: Path) -> bool:
    cmd = [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(media_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, **hidden_subprocess_kwargs())
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except Exception:
        pass
    result = subprocess.run([ffmpeg, "-i", str(media_path)], capture_output=True, text=True, **hidden_subprocess_kwargs())
    text = (result.stderr or "") + (result.stdout or "")
    return "Audio:" in text


def find_bgm_file() -> Optional[Path]:
    if not BGM_DIR.exists():
        return None
    candidates = []
    for pattern in ("*.mp3", "*.MP3", "*.wav", "*.WAV", "*.m4a", "*.M4A"):
        candidates.extend(BGM_DIR.glob(pattern))
    return random.choice(candidates) if candidates else None


def build_bgm_only_command(
    ffmpeg: str,
    input_video: Path,
    output_video: Path,
    bgm_file: Path,
    bgm_filter: str,
) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-i",
        str(input_video),
        "-stream_loop",
        "-1",
        "-i",
        str(bgm_file),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-af",
        bgm_filter,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_video),
    ]


def add_bgm_to_video(ffmpeg: str, ffprobe: str, input_video: Path, output_video: Path, bgm_file: Path, dry_run: bool, expected_duration: Optional[float] = None, fade_in: float = 1.0, fade_out: float = 1.5) -> None:
    measured_duration = get_media_duration(ffprobe, ffmpeg, input_video)
    duration = float(expected_duration) if expected_duration and expected_duration > 0 else measured_duration
    if not duration or duration <= 0:
        safe_print("Warning: Unable to determine video duration. Skipping BGM.")
        return

    fade_out_start = max(0.0, duration - fade_out)
    bgm_filter = f"volume={DEFAULT_BGM_VOLUME},afade=t=in:st=0:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}"
    input_has_audio = has_audio_stream(ffprobe, ffmpeg, input_video)
    bgm_only_cmd = build_bgm_only_command(ffmpeg, input_video, output_video, bgm_file, bgm_filter)

    if not input_has_audio:
        run_cmd(bgm_only_cmd, dry_run=dry_run)
        return

    if input_has_audio:
        filter_complex = f"[0:a]volume=0.45[src];[1:a]{bgm_filter}[bgm];[src][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]"
        map_audio = ["-map", "[a]"]
    else:
        filter_complex = f"[1:a]{bgm_filter}[a]"
        map_audio = ["-map", "[a]"]

    cmd = [ffmpeg, "-y", "-i", str(input_video), "-stream_loop", "-1", "-i", str(bgm_file), "-filter_complex", filter_complex, "-map", "0:v:0", *map_audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", str(duration), str(output_video)]
    try:
        run_cmd(cmd, dry_run=dry_run)
    except RuntimeError:
        run_cmd(bgm_only_cmd, dry_run=dry_run)
        return

    if not dry_run and not has_audio_stream(ffprobe, ffmpeg, output_video):
        safe_print("Warning: Primary BGM mix produced no audio, retrying with fallback mix.")
        run_cmd(bgm_only_cmd, dry_run=dry_run)


def render_subtitle(ffmpeg: str, input_video: Path, output_video: Path, subtitle_text: str, font_file: Optional[Path], font_size: int, max_line_len: int, dry_run: bool) -> None:
    font_size, max_line_len = resolve_subtitle_style(subtitle_text, font_size, max_line_len)
    subtitle_text = wrap_text(normalize_subtitle_text(subtitle_text), max_line_len)
    font_name = infer_font_name(font_file)
    subtitle_ass_file = write_ass_subtitle_file(output_video, subtitle_text, font_name, font_size)

    subtitles_filter = build_subtitles_filter(subtitle_ass_file, font_file)
    subtitles_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_video),
        "-vf",
        subtitles_filter,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(output_video),
    ]

    try:
        run_cmd(subtitles_cmd, dry_run=dry_run)
        return
    except RuntimeError:
        pass

    escaped_text = escape_drawtext_text(subtitle_text)

    filter_parts = []
    if font_file:
        filter_parts.append(f"fontfile={escape_drawtext_path(str(font_file))}")

    subtitle_file = output_video.with_suffix(".txt")
    subtitle_file.write_text(subtitle_text, encoding="utf-8-sig")
    subtitle_path = normalize_filter_path(subtitle_file)
    use_textfile = ":" not in subtitle_path.as_posix()
    if use_textfile:
        filter_parts.append(f"textfile={escape_drawtext_path(str(subtitle_path))}")
        filter_parts.append("reload=0")
    else:
        filter_parts.append(f"text='{escaped_text}'")

    filter_parts.extend(["x=(w-text_w)/2", "y=h*0.82", f"fontsize={font_size}", "line_spacing=10", "text_shaping=1", "fix_bounds=1", "fontcolor=white", "borderw=2", "bordercolor=black@0.35", "box=1", "boxcolor=black@0.45"])
    drawtext = "drawtext=" + ":".join(filter_parts)

    cmd = [ffmpeg, "-y", "-i", str(input_video), "-vf", drawtext, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(output_video)]
    run_cmd(cmd, dry_run=dry_run)


def transcode_clip(ffmpeg: str, input_video: Path, output_video: Path, dry_run: bool) -> None:
    cmd = [ffmpeg, "-y", "-i", str(input_video), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(output_video)]
    run_cmd(cmd, dry_run=dry_run)


def concat_videos_with_xfade(ffmpeg: str, input_videos: List[Path], clips: List[ClipSpec], output_video: Path, dry_run: bool) -> None:
    n = len(input_videos)
    if n < 2:
        raise ValueError("xfade requires at least 2 clips")

    inputs: list[str] = []
    for video in input_videos:
        inputs.extend(["-i", str(video)])

    video_filters = []
    for i in range(n):
        video_filters.append(f"[{i}:v]settb=AVTB,fps=30[v{i}]")

    current_offset = 0.0
    v_label = "v0"
    for i in range(n - 1):
        clip = clips[i]
        trans_type = clip.transition or "fade"
        trans_dur = min(clip.transition_duration, min(clip.duration, clips[i + 1].duration) / 2)
        current_offset += clip.duration - trans_dur
        out_v = f"xf{i}" if i < n - 2 else "vout"
        video_filters.append(f"[{v_label}][v{i + 1}]xfade=transition={trans_type}:duration={trans_dur:.3f}:offset={current_offset:.3f}[{out_v}]")
        v_label = out_v

    cmd = [ffmpeg, "-y", *inputs, "-filter_complex", ";".join(video_filters), "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(output_video)]
    safe_print(f"\n== Concatenating {n} clips with xfade transitions ==")
    run_cmd(cmd, dry_run=dry_run)


def concat_videos(ffmpeg: str, input_videos: List[Path], output_video: Path, temp_dir: Optional[Path], dry_run: bool) -> None:
    concat_list = (temp_dir / f"{output_video.stem}.concat.txt") if temp_dir else output_video.with_suffix(".concat.txt")
    concat_list.write_text("\n".join(quote_concat_path(path) for path in input_videos), encoding="utf-8")

    cmd_copy = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_video)]
    try:
        run_cmd(cmd_copy, dry_run=dry_run)
        return
    except RuntimeError:
        pass

    cmd_reencode = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(output_video)]
    try:
        run_cmd(cmd_reencode, dry_run=dry_run)
        return
    except RuntimeError:
        pass

    inputs: list[str] = []
    for video in input_videos:
        inputs.extend(["-i", str(video)])

    concat_v = "".join(f"[{idx}:v:0]" for idx in range(len(input_videos))) + f"concat=n={len(input_videos)}:v=1:a=0[v]"
    cmd_filter_v = [ffmpeg, "-y", *inputs, "-filter_complex", concat_v, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(output_video)]
    run_cmd(cmd_filter_v, dry_run=dry_run)


def resolve_output_dir(storyboard_path: Path, override: Optional[str]) -> Path:
    return Path(override) if override else storyboard_path.parent


def resolve_storyboard_input(storyboard_input: Path) -> Path:
    if storyboard_input.is_file():
        return storyboard_input

    if storyboard_input.is_dir():
        legacy_candidate = storyboard_input / LEGACY_STORYBOARD_FILE_NAME
        if legacy_candidate.exists():
            return legacy_candidate

        named_candidates = sorted(storyboard_input.glob(f"*{STORYBOARD_FILE_SUFFIX}"))
        if len(named_candidates) == 1:
            return named_candidates[0]
        if len(named_candidates) > 1:
            raise ValueError(f"目录下找到多个 storyboard 文件，请显式指定文件：{storyboard_input}")
        raise FileNotFoundError(f"目录下未找到 storyboard 文件：{storyboard_input}")

    raise FileNotFoundError(f"storyboard 文件或目录不存在：{storyboard_input}")


def build_final_output_name(meta: StoryboardMeta, clips: List[ClipSpec]) -> str:
    theme = sanitize_filename_component(meta.theme, "video")
    duration = sanitize_filename_component(format_duration_component(meta.target_duration, meta.actual_duration, clips), "unknown")
    return f"{theme}_{duration}_bgm.mp4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 storyboard.json 抽取片段、加字幕并合成成片")
    parser.add_argument("--storyboard", required=True, help="storyboard JSON 路径，或包含 storyboard 的目录")
    parser.add_argument("--ffmpeg", default=None, help="ffmpeg 路径")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument("--font_file", "--font-file", dest="font_file", default=None, help="字幕字体文件路径")
    parser.add_argument("--font-size", type=int, default=DEFAULT_SUBTITLE_FONT_SIZE, help="字幕字号")
    parser.add_argument("--max-line-len", type=int, default=DEFAULT_SUBTITLE_MAX_LINE_LEN, help="每行最大字数")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 ffmpeg 命令")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_local_requirements(force=False)
        maybe_reexec_in_local_venv("ov_video_editing_skills.compose_video")
    except Exception as exc:
        safe_print(f"Error: failed to validate current Python environment: {exc}", file=sys.stderr)
        return 1

    if not args.ffmpeg:
        args.ffmpeg = find_default_ffmpeg()

    try:
        storyboard_path = resolve_storyboard_input(Path(args.storyboard).resolve())
    except Exception as exc:
        safe_print(f"Error: {exc}", file=sys.stderr)
        return 1

    clips, storyboard_bgm, meta = load_storyboard(storyboard_path)

    output_dir = resolve_output_dir(storyboard_path, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    font_file = None
    if args.font_file:
        candidate = Path(args.font_file)
        if candidate.exists():
            font_file = normalize_filter_path(candidate)
        else:
            safe_print(f"Warning: Font file not found: {candidate}")
    if not font_file:
        font_file = find_default_font()
    subtitles_enabled = font_file is not None
    if not subtitles_enabled:
        safe_print("Warning: No font file found. Subtitles will be skipped.")

    processed_files: List[Path] = []
    for clip in clips:
        base = f"clip_{clip.sequence_order:02d}_id{clip.clip_id}"
        raw_path = temp_dir / f"{base}_raw.mp4"
        subtitle_path = temp_dir / f"{base}_sub.mp4"
        safe_print(f"\n== Processing clip {clip.sequence_order} (clip_id={clip.clip_id}) ==")
        extract_clip(args.ffmpeg, clip.source_video, raw_path, clip.in_point, clip.duration, args.dry_run)
        if clip.subtitle and subtitles_enabled:
            render_subtitle(args.ffmpeg, raw_path, subtitle_path, clip.subtitle, font_file, args.font_size, args.max_line_len, args.dry_run)
        else:
            transcode_clip(args.ffmpeg, raw_path, subtitle_path, args.dry_run)
        processed_files.append(subtitle_path)

    final_output = temp_dir / "merged_no_bgm.mp4"
    has_transitions = any(clip.transition for clip in clips)
    if has_transitions and len(processed_files) >= 2:
        try:
            concat_videos_with_xfade(args.ffmpeg, processed_files, clips, final_output, args.dry_run)
        except Exception as exc:
            safe_print(f"\nWarning: xfade failed ({exc}), falling back to hard-cut concat.")
            concat_videos(args.ffmpeg, processed_files, final_output, temp_dir, args.dry_run)
    else:
        safe_print(f"\n== Concatenating {len(processed_files)} clips ==")
        concat_videos(args.ffmpeg, processed_files, final_output, temp_dir, args.dry_run)

    total_clip_duration = sum(clip.duration for clip in clips)
    overlap = sum(clip.transition_duration for clip in clips[:-1] if clip.transition)
    expected_dur = total_clip_duration - overlap if has_transitions else total_clip_duration

    ffprobe = resolve_ffprobe(args.ffmpeg)
    bgm_file = storyboard_bgm or find_bgm_file()
    if storyboard_bgm and not storyboard_bgm.exists():
        safe_print(f"\nWarning: Storyboard BGM not found: {storyboard_bgm}. Falling back to random selection.")
        bgm_file = find_bgm_file()

    bgm_output = output_dir / build_final_output_name(meta, clips)
    if bgm_file:
        safe_print(f"\n== Adding BGM: {bgm_file} ==")
        add_bgm_to_video(args.ffmpeg, ffprobe, final_output, bgm_output, bgm_file, args.dry_run, expected_duration=expected_dur)
    else:
        safe_print("\nWarning: No BGM mp3 found. Copying non-BGM output to final name.")
        if not args.dry_run:
            shutil.copy2(final_output, bgm_output)

    safe_print(f"\nDone. Intermediate (no BGM): {final_output}")
    safe_print(f"Done. Final output: {bgm_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
