from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TARGET_DURATION = 30.0
DEFAULT_THEME = "日常记录"
DEFAULT_MOOD = "轻松自然"
DEFAULT_PACING = "连贯流畅"
DEFAULT_ANALYSIS_PROMPT = (
    "准确的描述这个视频片段中的主要内容，包括：场景环境、人物动作、"
    "画面构图、光线氛围、运镜方式。输出不超过100字的简要描述。"
)
REQUIREMENT_PROMPT_TEMPLATE = (
    "请根据以下剪辑目标分析视频片段：主题是「{theme}」，氛围是「{mood}」，"
    "节奏要求「{pacing}」。重点捕捉与「{must_capture}」相关的画面线索。"
    "描述中必须包含：场景环境、人物动作、画面构图、光线氛围、运镜方式，"
    "并突出与目标风格相关的信息。输出不超过100字。"
)
BRIEF_FILE_NAME = "creative_brief.json"


@dataclass
class CreativeBrief:
    user_request: str = ""
    target_duration_seconds: float = DEFAULT_TARGET_DURATION
    theme: str = DEFAULT_THEME
    mood: str = DEFAULT_MOOD
    pacing: str = DEFAULT_PACING
    must_capture: list[str] = field(default_factory=list)
    prompt_mode: str = "default"
    analysis_prompt: str = DEFAULT_ANALYSIS_PROMPT
    request_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_duration_seconds"] = float(self.target_duration_seconds)
        return payload


_DURATION_PATTERNS = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒钟|秒|s|sec)", re.IGNORECASE), 1.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|mins?|minutes?)", re.IGNORECASE), 60.0),
]
_LABEL_PATTERNS = {
    "theme": [r"主题(?:是|为)?[：: ]+([^，。；\n]+)", r"做(?:一个|一条)?([^，。；\n]+?)(?:vlog|视频)"],
    "mood": [r"氛围(?:是|为)?[：: ]+([^，。；\n]+)", r"风格(?:是|为)?[：: ]+([^，。；\n]+)"],
    "pacing": [r"节奏(?:是|为)?[：: ]+([^，。；\n]+)"],
}
_MUST_CAPTURE_PATTERNS = [
    r"(?:必须|一定|务必|重点)(?:捕捉|保留|突出|包含)([^。；\n]+)",
    r"必选内容[：: ]+([^。；\n]+)",
    r"重点内容[：: ]+([^。；\n]+)",
]
_KEYWORD_CANDIDATES = [
    "旅行", "城市", "街头", "咖啡", "落日", "夜景", "朋友", "家人", "宠物",
    "海边", "公路", "山", "雨天", "烟火", "日常", "探店", "徒步", "运动",
]


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ，,。；;\n\t")


def _extract_duration_seconds(user_request: str) -> float | None:
    for pattern, multiplier in _DURATION_PATTERNS:
        match = pattern.search(user_request)
        if match:
            return float(match.group(1)) * multiplier
    return None


def _extract_label(user_request: str, field_name: str) -> str | None:
    for pattern in _LABEL_PATTERNS[field_name]:
        match = re.search(pattern, user_request, re.IGNORECASE)
        if match:
            value = _clean_text(match.group(1))
            if value:
                return value
    return None


def _split_keywords(raw: str) -> list[str]:
    normalized = re.sub(r"[、/|；;，,和及]+", "|", raw)
    return [item for item in (_clean_text(part) for part in normalized.split("|")) if item]


def _extract_must_capture(user_request: str) -> list[str]:
    keywords: list[str] = []
    for pattern in _MUST_CAPTURE_PATTERNS:
        for match in re.finditer(pattern, user_request, re.IGNORECASE):
            keywords.extend(_split_keywords(match.group(1)))
    unique: list[str] = []
    for item in keywords:
        if item not in unique:
            unique.append(item)
    return unique


def _extract_request_keywords(user_request: str) -> list[str]:
    found = [token for token in _KEYWORD_CANDIDATES if token in user_request]
    return found[:8]


def build_analysis_prompt(brief: CreativeBrief) -> str:
    if brief.prompt_mode != "requirements":
        return DEFAULT_ANALYSIS_PROMPT
    must_capture = "、".join(brief.must_capture) if brief.must_capture else "叙事重点"
    return REQUIREMENT_PROMPT_TEMPLATE.format(
        theme=brief.theme,
        mood=brief.mood,
        pacing=brief.pacing,
        must_capture=must_capture,
    )


def create_creative_brief(user_request: str | None) -> CreativeBrief:
    request_text = _clean_text(user_request)
    duration = _extract_duration_seconds(request_text) or DEFAULT_TARGET_DURATION
    theme = _extract_label(request_text, "theme") or DEFAULT_THEME
    mood = _extract_label(request_text, "mood") or DEFAULT_MOOD
    pacing = _extract_label(request_text, "pacing") or DEFAULT_PACING
    must_capture = _extract_must_capture(request_text)
    keywords = _extract_request_keywords(request_text)

    has_explicit_request = bool(request_text)
    has_custom_constraints = any(
        [
            duration != DEFAULT_TARGET_DURATION,
            theme != DEFAULT_THEME,
            mood != DEFAULT_MOOD,
            pacing != DEFAULT_PACING,
            bool(must_capture),
        ]
    )
    prompt_mode = "requirements" if has_explicit_request and has_custom_constraints else "default"

    brief = CreativeBrief(
        user_request=request_text,
        target_duration_seconds=duration,
        theme=theme,
        mood=mood,
        pacing=pacing,
        must_capture=must_capture,
        prompt_mode=prompt_mode,
        request_keywords=keywords,
    )
    brief.analysis_prompt = build_analysis_prompt(brief)
    return brief


def save_creative_brief(workspace_dir: Path, brief: CreativeBrief) -> Path:
    path = workspace_dir / BRIEF_FILE_NAME
    path.write_text(json.dumps(brief.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_creative_brief(path: Path) -> CreativeBrief:
    data = json.loads(path.read_text(encoding="utf-8"))
    brief = CreativeBrief(
        user_request=_clean_text(data.get("user_request")),
        target_duration_seconds=float(data.get("target_duration_seconds", DEFAULT_TARGET_DURATION)),
        theme=_clean_text(data.get("theme")) or DEFAULT_THEME,
        mood=_clean_text(data.get("mood")) or DEFAULT_MOOD,
        pacing=_clean_text(data.get("pacing")) or DEFAULT_PACING,
        must_capture=[_clean_text(item) for item in data.get("must_capture", []) if _clean_text(item)],
        prompt_mode=_clean_text(data.get("prompt_mode")) or "default",
        request_keywords=[_clean_text(item) for item in data.get("request_keywords", []) if _clean_text(item)],
    )
    brief.analysis_prompt = _clean_text(data.get("analysis_prompt")) or build_analysis_prompt(brief)
    return brief


def discover_creative_brief(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is None:
            continue
        candidate = path if path.name == BRIEF_FILE_NAME else path.parent / BRIEF_FILE_NAME
        if candidate.exists():
            return candidate
    return None
