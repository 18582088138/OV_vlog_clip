from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..e2e import DEFAULT_REQUEST


class TaskName(str, Enum):
    PREPARE = "prepare"
    ANALYZE = "analyze"
    STORYBOARD = "storyboard"
    COMPOSE = "compose"
    E2E = "e2e"


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class TaskConfig:
    video_input: str = ""
    user_request: str = DEFAULT_REQUEST
    output_dir: str = ""
    model_dir: str = ""
    ffmpeg_path: str = ""
    font_file: str = ""
    bgm_file: str = ""
    bgm_style: str = ""
    brief_path: str = ""
    analysis_path: str = ""
    storyboard_path: str = ""
    device: str = "GPU"
    ignore_existing_analysis: bool = False
    skip_ffmpeg: bool = False
    skip_model: bool = False

    def as_persisted_dict(self) -> dict[str, Any]:
        return {
            "video_input": self.video_input,
            "user_request": self.user_request,
            "output_dir": self.output_dir,
            "model_dir": self.model_dir,
            "ffmpeg_path": self.ffmpeg_path,
            "font_file": self.font_file,
            "bgm_file": self.bgm_file,
            "bgm_style": self.bgm_style,
            "brief_path": self.brief_path,
            "analysis_path": self.analysis_path,
            "storyboard_path": self.storyboard_path,
            "device": self.device,
            "ignore_existing_analysis": self.ignore_existing_analysis,
            "skip_ffmpeg": self.skip_ffmpeg,
            "skip_model": self.skip_model,
        }

    @classmethod
    def from_persisted_dict(cls, payload: dict[str, Any] | None) -> "TaskConfig":
        payload = payload or {}
        return cls(
            video_input=str(payload.get("video_input") or ""),
            user_request=str(payload.get("user_request") or DEFAULT_REQUEST),
            output_dir=str(payload.get("output_dir") or ""),
            model_dir=str(payload.get("model_dir") or ""),
            ffmpeg_path=str(payload.get("ffmpeg_path") or ""),
            font_file=str(payload.get("font_file") or ""),
            bgm_file=str(payload.get("bgm_file") or ""),
            bgm_style=str(payload.get("bgm_style") or ""),
            brief_path=str(payload.get("brief_path") or ""),
            analysis_path=str(payload.get("analysis_path") or ""),
            storyboard_path=str(payload.get("storyboard_path") or ""),
            device=str(payload.get("device") or "GPU"),
            ignore_existing_analysis=bool(payload.get("ignore_existing_analysis", False)),
            skip_ffmpeg=bool(payload.get("skip_ffmpeg", False)),
            skip_model=bool(payload.get("skip_model", False)),
        )


@dataclass
class TaskResult:
    task_name: TaskName
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


@dataclass
class WorkspaceArtifact:
    key: str
    label: str
    path: str
    exists: bool
    description: str = ""

    def path_obj(self) -> Path | None:
        if not self.path:
            return None
        return Path(self.path)


@dataclass
class EnvironmentCheck:
    key: str
    label: str
    status: str
    detail: str
    suggestion: str = ""
    blocking: bool = False


@dataclass
class DiagnosticIssue:
    key: str
    severity: str
    summary: str
    detail: str
    suggestion: str = ""


@dataclass
class AppState:
    config: TaskConfig = field(default_factory=TaskConfig)
    status: TaskStatus = TaskStatus.IDLE
    last_task: TaskName | None = None
    last_result: TaskResult | None = None
    workspace_dir: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)

    def append_log(self, text: str) -> None:
        normalized = str(text).rstrip("\n")
        if normalized:
            self.log_lines.append(normalized)

    def workspace_path(self) -> Path | None:
        if not self.workspace_dir:
            return None
        return Path(self.workspace_dir)