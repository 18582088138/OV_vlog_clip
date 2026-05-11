from __future__ import annotations

import argparse
import json
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .creative_brief import (
    DEFAULT_MOOD,
    DEFAULT_PACING,
    DEFAULT_TARGET_DURATION,
    DEFAULT_THEME,
    CreativeBrief,
    LEGACY_STORYBOARD_FILE_NAME,
    ANALYSIS_FILE_SUFFIX,
    build_storyboard_file_name,
    discover_creative_brief,
    infer_base_name_from_artifact,
    load_creative_brief,
)
from .runtime import BGM_DIR

INVALID_SEGMENT_TERMS = ("分析失败", "无法提取帧", "未生成有效描述")
LEGACY_ANALYSIS_FILE_NAME = "output_vlm.json"


@dataclass
class SegmentCandidate:
    source_video: str
    seg_id: int
    seg_start: float
    seg_end: float
    seg_dur: float
    seg_desc: str
    score: float


def resolve_story_phase(index: int, total: int) -> str:
    if total <= 1:
        return "single"
    ratio = index / total
    if ratio <= 0.25:
        return "opening"
    if ratio <= 0.6:
        return "development"
    if ratio <= 0.85:
        return "highlight"
    return "ending"


def build_caption(candidate: SegmentCandidate, phase: str, theme: str, mood: str) -> str:
    summary = summarize_caption(candidate.seg_desc, max_length=18)
    templates = {
        "opening": f"从{theme}的开场进入，{summary}",
        "development": f"情绪慢慢展开，{summary}",
        "highlight": f"这一刻最有{mood}感，{summary}",
        "ending": f"最后把感受留在画面里，{summary}",
        "single": summary,
    }
    text = templates.get(phase, summary)
    return text[:28].rstrip("，,；;。.")


def derive_emotional_arc(mood: str, pacing: str) -> str:
    if any(token in mood for token in ["热烈", "兴奋", "活力"]):
        return "期待→升温→释放"
    if any(token in pacing for token in ["慢", "舒缓", "治愈"]):
        return "观察→沉浸→回味"
    return "进入→展开→收束"


def load_optional_brief(brief_path: Path | None) -> CreativeBrief | None:
    if not brief_path or not brief_path.exists():
        return None
    return load_creative_brief(brief_path)


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.replace("，", "，").replace("。", "。")
    return text


def is_valid_segment(desc: str) -> bool:
    clean = normalize_text(desc)
    if len(clean) < 10:
        return False
    return not any(term in clean for term in INVALID_SEGMENT_TERMS)


def score_segment(desc: str, must_capture: list[str]) -> float:
    clean = normalize_text(desc)
    score = min(len(clean), 80) / 10.0
    if any(keyword and keyword in clean for keyword in must_capture):
        score += 4.0
    if any(token in clean for token in ["人物", "动作", "街道", "天空", "光线", "构图", "笑", "风景", "运动"]):
        score += 1.0
    return score


def load_analysis(path: Path, must_capture: list[str]) -> list[SegmentCandidate]:
    data = json.loads(path.read_text(encoding="utf-8"))
    processed_videos = data.get("processed_videos") or []
    candidates: list[SegmentCandidate] = []
    for video in processed_videos:
        source_video = str(video.get("input_video", ""))
        for segment in video.get("segments") or []:
            desc = str(segment.get("seg_desc", "")).strip()
            if not is_valid_segment(desc):
                continue
            candidates.append(
                SegmentCandidate(
                    source_video=source_video,
                    seg_id=int(segment.get("seg_id", 0)),
                    seg_start=float(segment.get("seg_start", 0.0)),
                    seg_end=float(segment.get("seg_end", 0.0)),
                    seg_dur=float(segment.get("seg_dur", 0.0)),
                    seg_desc=desc,
                    score=score_segment(desc, must_capture),
                )
            )
    return candidates


def infer_theme(theme: str | None, candidates: list[SegmentCandidate]) -> str:
    if theme:
        return theme
    if not candidates:
        return DEFAULT_THEME
    merged = " ".join(candidate.seg_desc for candidate in candidates[:6])
    if any(token in merged for token in ["公路", "开车", "山路", "旅行", "风景"]):
        return "旅行片段"
    if any(token in merged for token in ["咖啡", "街头", "城市", "商场"]):
        return "城市漫步"
    if any(token in merged for token in ["家庭", "亲子", "宠物"]):
        return "温馨日常"
    return DEFAULT_THEME


def pick_evenly(candidates: list[SegmentCandidate], target_count: int) -> list[SegmentCandidate]:
    if target_count >= len(candidates):
        return candidates
    selected: list[SegmentCandidate] = []
    used: set[tuple[str, int]] = set()
    step = len(candidates) / target_count
    for index in range(target_count):
        position = min(len(candidates) - 1, round(index * step))
        candidate = candidates[position]
        key = (candidate.source_video, candidate.seg_id)
        if key in used:
            continue
        used.add(key)
        selected.append(candidate)
    if len(selected) < target_count:
        for candidate in candidates:
            key = (candidate.source_video, candidate.seg_id)
            if key not in used:
                selected.append(candidate)
                used.add(key)
            if len(selected) >= target_count:
                break
    return selected[:target_count]


def select_candidates(candidates: list[SegmentCandidate], target_duration: float) -> list[SegmentCandidate]:
    if not candidates:
        return []
    avg_duration = sum(max(candidate.seg_dur, 0.1) for candidate in candidates) / len(candidates)
    target_count = max(4, min(len(candidates), math.ceil(target_duration / max(avg_duration, 0.1))))
    candidates_sorted = sorted(candidates, key=lambda item: (-item.score, item.source_video, item.seg_start))
    top_pool = candidates_sorted[: max(target_count * 3, target_count)]
    top_pool = sorted(top_pool, key=lambda item: (item.source_video, item.seg_start))
    return pick_evenly(top_pool, target_count)


def summarize_caption(desc: str, max_length: int = 20) -> str:
    clean = normalize_text(desc)
    clean = re.split(r"[。！？!?.]", clean)[0]
    clean = clean.strip("，,;； ")
    if len(clean) <= max_length:
        return clean
    return clean[:max_length].rstrip("，,;； ") + "…"


def resolve_transition(pacing: str, index: int, total: int) -> tuple[str, float]:
    if index >= total - 1:
        return "", 0.0
    pace = pacing or DEFAULT_PACING
    if any(token in pace for token in ["快", "动感", "活力"]):
        transitions = ["smoothleft", "smoothright", "fade"]
        return transitions[index % len(transitions)], 0.6
    if any(token in pace for token in ["慢", "舒缓", "治愈"]):
        transitions = ["dissolve", "fade", "fadewhite"]
        return transitions[index % len(transitions)], 1.0
    transitions = ["fade", "dissolve"]
    return transitions[index % len(transitions)], 0.8


def load_bgm_style_index() -> dict[str, Any]:
    bgm_index_path = BGM_DIR / "bgm_style.json"
    if not bgm_index_path.exists():
        return {}
    try:
        return json.loads(bgm_index_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return json.loads(bgm_index_path.read_text(encoding="utf-8"))


def infer_bgm_style(mood: str, explicit_style: str | None) -> str | None:
    if explicit_style:
        return explicit_style
    mood = mood or DEFAULT_MOOD
    if any(token in mood for token in ["浪漫", "温馨", "柔和"]):
        return "温馨浪漫"
    if any(token in mood for token in ["舒缓", "放松", "治愈"]):
        return "舒缓优美"
    if any(token in mood for token in ["轻松", "明快", "愉悦", "旅行"]):
        return "轻松愉悦"
    return None


def choose_bgm_file(mood: str, bgm_style: str | None, bgm_file: str | None) -> tuple[str | None, str | None]:
    if bgm_file:
        candidate = Path(bgm_file)
        if candidate.exists():
            return candidate.name if candidate.parent == BGM_DIR else str(candidate), bgm_style
        local_candidate = BGM_DIR / bgm_file
        if local_candidate.exists():
            return local_candidate.name, bgm_style

    existing_mp3 = sorted([path.name for path in BGM_DIR.glob("*.mp3")])
    if not existing_mp3:
        return None, infer_bgm_style(mood, bgm_style)

    selected_style = infer_bgm_style(mood, bgm_style)
    style_index = load_bgm_style_index()
    if selected_style and selected_style in style_index:
        for file_name in style_index[selected_style].keys():
            if file_name in existing_mp3:
                return file_name, selected_style

    return random.choice(existing_mp3), selected_style


def build_story_outline(theme: str, mood: str, candidates: list[SegmentCandidate]) -> dict[str, str]:
    summary_parts = [candidate.seg_desc for candidate in candidates[:3]]
    return {
        "title": theme,
        "summary": "；".join(summary_parts)[:160],
        "narrative_angle": f"以{mood}的方式串联片段，突出 vlog 的现场感和节奏感。",
    }


def generate_storyboard(
    analysis_path: Path,
    output_path: Path,
    target_duration: float | None,
    theme: str | None,
    mood: str | None,
    pacing: str | None,
    must_capture: list[str],
    bgm_style: str | None,
    bgm_file: str | None,
    brief_path: Path | None = None,
) -> dict[str, Any]:
    brief = load_optional_brief(brief_path)
    effective_target_duration = target_duration or (brief.target_duration_seconds if brief else DEFAULT_TARGET_DURATION)
    effective_theme = theme or (brief.theme if brief else None)
    effective_mood = mood or (brief.mood if brief else None)
    effective_pacing = pacing or (brief.pacing if brief else None)
    effective_must_capture = must_capture or (brief.must_capture if brief else [])

    candidates = load_analysis(analysis_path, effective_must_capture)
    if not candidates:
        raise ValueError("未从 output_vlm.json 中找到可用片段")

    selected = select_candidates(candidates, effective_target_duration)
    final_theme = infer_theme(effective_theme, selected)
    final_mood = effective_mood or DEFAULT_MOOD
    final_pacing = effective_pacing or DEFAULT_PACING
    selected_bgm, selected_style = choose_bgm_file(final_mood, bgm_style, bgm_file)

    clips = []
    total_duration = 0.0
    overlap_total = 0.0
    for index, candidate in enumerate(selected, start=1):
        phase = resolve_story_phase(index, len(selected))
        transition_name, transition_duration = resolve_transition(final_pacing, index - 1, len(selected))
        if transition_name:
            overlap_total += transition_duration
        total_duration += candidate.seg_dur
        clips.append(
            {
                "clip_id": candidate.seg_id,
                "sequence_order": index,
                "source_video": candidate.source_video,
                "timecode": {
                    "in_point": round(candidate.seg_start, 3),
                    "out_point": round(candidate.seg_end, 3),
                    "duration": round(candidate.seg_dur, 3),
                },
                "narrative_role": phase,
                "voiceover": {
                    "text": build_caption(candidate, phase, final_theme, final_mood),
                },
                "transition": {
                    "type": transition_name,
                    "duration": transition_duration,
                },
                "analysis_ref": {
                    "seg_desc": candidate.seg_desc,
                },
            }
        )

    actual_duration = max(total_duration - overlap_total, 0.0)
    storyboard = {
        "storyboard_metadata": {
            "theme": final_theme,
            "mood": final_mood,
            "pacing": final_pacing,
            "target_duration_seconds": effective_target_duration,
            "actual_duration_seconds": round(actual_duration, 3),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_analysis": str(analysis_path),
            "creative_brief": str(brief_path) if brief_path else "",
        },
        "story_outline": build_story_outline(final_theme, final_mood, selected)
        | {
            "emotional_arc": derive_emotional_arc(final_mood, final_pacing),
            "must_capture": effective_must_capture,
        },
        "audio_design": {
            "background_music": {
                "style_tag": selected_style or "",
                "file_path": selected_bgm or "",
            }
        },
        "clips": clips,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")
    return storyboard


def resolve_analysis_input(analysis_input: Path) -> Path:
    if analysis_input.is_file():
        return analysis_input

    if analysis_input.is_dir():
        legacy_candidate = analysis_input / LEGACY_ANALYSIS_FILE_NAME
        if legacy_candidate.exists():
            return legacy_candidate

        named_candidates = sorted(analysis_input.glob(f"*{ANALYSIS_FILE_SUFFIX}"))
        if len(named_candidates) == 1:
            return named_candidates[0]
        if len(named_candidates) > 1:
            raise ValueError(f"目录下找到多个分析结果，请显式指定文件：{analysis_input}")
        raise FileNotFoundError(f"目录下未找到分析结果文件：{analysis_input}")

    raise FileNotFoundError(f"分析结果文件或目录不存在：{analysis_input}")


def resolve_storyboard_output_path(explicit_output: str | None, analysis_path: Path) -> Path:
    if explicit_output:
        return Path(explicit_output).resolve()

    base_name = infer_base_name_from_artifact(analysis_path) or analysis_path.parent.name or "video"
    return analysis_path.parent / build_storyboard_file_name(base_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 output_vlm.json 生成本地 storyboard.json")
    parser.add_argument("--analysis", required=True, help="分析结果 JSON 路径，或包含分析结果的目录")
    parser.add_argument("--output", required=False, help="storyboard.json 输出路径；未传时按分析文件名自动生成")
    parser.add_argument("--target-duration", type=float, default=None, help="目标成片时长（秒）；未传时优先读取 creative_brief.json")
    parser.add_argument("--theme", default=None, help="主题")
    parser.add_argument("--mood", default=None, help="氛围")
    parser.add_argument("--pacing", default=None, help="节奏")
    parser.add_argument("--must-capture", nargs="*", default=[], help="必须捕捉的关键词，可传多个")
    parser.add_argument("--bgm-style", default=None, help="指定 BGM 风格标签")
    parser.add_argument("--bgm-file", default=None, help="指定 BGM 文件名或绝对路径")
    parser.add_argument("--brief", default=None, help="brief JSON 路径，支持 legacy `creative_brief.json` 或 `<video_name>_brief.json`")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        analysis_path = resolve_analysis_input(Path(args.analysis).resolve())
        output_path = resolve_storyboard_output_path(args.output, analysis_path)
    except Exception as exc:
        print(f"[storyboard] ✗ 失败：{exc}")
        return 1

    brief_path = discover_creative_brief(Path(args.brief).resolve() if args.brief else None, analysis_path, output_path)

    try:
        storyboard = generate_storyboard(
            analysis_path=analysis_path,
            output_path=output_path,
            target_duration=args.target_duration,
            theme=args.theme,
            mood=args.mood,
            pacing=args.pacing,
            must_capture=[item.strip() for item in args.must_capture if item.strip()],
            bgm_style=args.bgm_style,
            bgm_file=args.bgm_file,
            brief_path=brief_path,
        )
    except Exception as exc:
        print(f"[storyboard] ✗ 失败：{exc}")
        return 1

    print(f"[storyboard] 使用分析结果：{analysis_path}")
    print(f"[storyboard] ✓ 已生成：{output_path}")
    if brief_path:
        print(f"[storyboard] 使用 brief：{brief_path}")
    print(json.dumps(storyboard.get("storyboard_metadata", {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
