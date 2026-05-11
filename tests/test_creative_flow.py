from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ov_video_editing_skills import analyze_video
from ov_video_editing_skills import cli
from ov_video_editing_skills.bootstrap import bootstrap_environment
from ov_video_editing_skills.compose_video import resolve_storyboard_input
from ov_video_editing_skills.creative_brief import (
    build_analysis_file_name,
    build_brief_file_name,
    build_storyboard_file_name,
    create_creative_brief,
    save_creative_brief,
)
from ov_video_editing_skills.generate_storyboard import generate_storyboard, resolve_analysis_input, resolve_storyboard_output_path
from ov_video_editing_skills.prepare_workspace import prepare_workspace
from ov_video_editing_skills.runtime import runtime_summary


class CreativeFlowTests(unittest.TestCase):
    def test_create_brief_extracts_request_preferences(self) -> None:
        brief = create_creative_brief(
            "做一个45秒的旅行vlog，主题：海边落日，氛围：轻松治愈，节奏：舒缓，重点保留海浪、晚霞、人物背影"
        )

        self.assertEqual(brief.target_duration_seconds, 45.0)
        self.assertEqual(brief.theme, "海边落日")
        self.assertEqual(brief.mood, "轻松治愈")
        self.assertEqual(brief.pacing, "舒缓")
        self.assertIn("海浪", brief.must_capture)
        self.assertEqual(brief.prompt_mode, "requirements")
        self.assertIn("海浪", brief.analysis_prompt)

    def test_storyboard_inherits_brief_when_args_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            video_path = workspace / "sample.mp4"
            video_path.write_bytes(b"fake")

            analysis_path = workspace / "output_vlm.json"
            analysis_path.write_text(
                json.dumps(
                    {
                        "processed_videos": [
                            {
                                "input_video": str(video_path),
                                "segments": [
                                    {
                                        "seg_id": 0,
                                        "seg_start": 0.0,
                                        "seg_end": 3.0,
                                        "seg_dur": 3.0,
                                        "seg_desc": "海边人物迎着晚霞慢慢走向镜头，画面温柔而安静。",
                                    },
                                    {
                                        "seg_id": 1,
                                        "seg_start": 3.0,
                                        "seg_end": 6.0,
                                        "seg_dur": 3.0,
                                        "seg_desc": "海浪反复拍打礁石，天空被夕阳染成金色，构图开阔。",
                                    },
                                    {
                                        "seg_id": 2,
                                        "seg_start": 6.0,
                                        "seg_end": 9.0,
                                        "seg_dur": 3.0,
                                        "seg_desc": "镜头掠过沙滩脚印和远处背影，氛围宁静，节奏舒缓。",
                                    },
                                    {
                                        "seg_id": 3,
                                        "seg_start": 9.0,
                                        "seg_end": 12.0,
                                        "seg_dur": 3.0,
                                        "seg_desc": "人物停下回头看海，光线柔和，情绪像被晚风拉长。",
                                    },
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            brief = create_creative_brief(
                "做一个24秒的旅行vlog，主题：海边落日，氛围：轻松治愈，节奏：舒缓，重点保留海浪、晚霞"
            )
            brief_path = save_creative_brief(workspace, brief)
            storyboard_path = workspace / "storyboard.json"

            storyboard = generate_storyboard(
                analysis_path=analysis_path,
                output_path=storyboard_path,
                target_duration=None,
                theme=None,
                mood=None,
                pacing=None,
                must_capture=[],
                bgm_style=None,
                bgm_file=None,
                brief_path=brief_path,
            )

            self.assertEqual(storyboard["storyboard_metadata"]["theme"], "海边落日")
            self.assertEqual(storyboard["storyboard_metadata"]["pacing"], "舒缓")
            self.assertEqual(storyboard["storyboard_metadata"]["target_duration_seconds"], 24.0)
            self.assertEqual(storyboard["story_outline"]["must_capture"], ["海浪", "晚霞"])
            self.assertTrue(storyboard["clips"])
            self.assertTrue(storyboard_path.exists())

    def test_prepare_workspace_reuses_existing_analysis_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = Path(tmp)
            (video_dir / "clip01.mp4").write_bytes(b"fake-video")
            existing_analysis = video_dir / build_analysis_file_name("clip01")
            existing_analysis.write_text(
                json.dumps(
                    {
                        "processed_videos": [
                            {
                                "input_video": str(video_dir / "clip01.mp4"),
                                "segments": [
                                    {
                                        "seg_id": 0,
                                        "seg_start": 0.0,
                                        "seg_end": 3.0,
                                        "seg_dur": 3.0,
                                        "seg_desc": "街头行走镜头，人物动作自然，光线明亮。",
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with patch(
                "ov_video_editing_skills.prepare_workspace.bootstrap_environment",
                return_value={"venv_python": "conda://ov_env/python", "ffmpeg": "bin/ffmpeg.exe"},
            ):
                workspace, _, analysis_info = prepare_workspace(
                    video_dir=video_dir,
                    user_request="做一个30秒的城市漫步vlog",
                )

            staged_analysis = workspace / build_analysis_file_name("clip01")
            brief_path = workspace / build_brief_file_name("clip01")
            runtime_manifest = json.loads((workspace / "runtime_env.json").read_text(encoding="utf-8"))

            self.assertEqual(analysis_info["analysis_mode"], "reuse_existing_output")
            self.assertTrue(staged_analysis.exists())
            self.assertTrue(brief_path.exists())
            self.assertEqual(staged_analysis.read_text(encoding="utf-8"), existing_analysis.read_text(encoding="utf-8"))
            self.assertEqual(runtime_manifest["analysis_mode"], "reuse_existing_output")
            self.assertEqual(runtime_manifest["analysis_segment_count"], 1)
            self.assertEqual(runtime_manifest["artifact_base_name"], "clip01")
            self.assertEqual(Path(runtime_manifest["creative_brief"]), brief_path)

    def test_prepare_workspace_can_ignore_existing_analysis_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = Path(tmp)
            (video_dir / "clip01.mp4").write_bytes(b"fake-video")
            (video_dir / build_analysis_file_name("clip01")).write_text(
                json.dumps(
                    {
                        "processed_videos": [
                            {
                                "input_video": str(video_dir / "clip01.mp4"),
                                "segments": [{"seg_id": 0, "seg_start": 0.0, "seg_end": 3.0, "seg_dur": 3.0, "seg_desc": "test"}],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "ov_video_editing_skills.prepare_workspace.bootstrap_environment",
                return_value={"venv_python": "conda://ov_env/python", "ffmpeg": "bin/ffmpeg.exe"},
            ):
                workspace, _, analysis_info = prepare_workspace(
                    video_dir=video_dir,
                    user_request="做一个30秒的日常vlog",
                    ignore_existing_analysis=True,
                )

            self.assertEqual(analysis_info["analysis_mode"], "ignore_existing_output")
            self.assertFalse((workspace / build_analysis_file_name("clip01")).exists())

    def test_prepare_workspace_accepts_single_video_file_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            video_file = workspace_root / "clip01.mp4"
            video_file.write_bytes(b"fake-video")

            with patch(
                "ov_video_editing_skills.prepare_workspace.bootstrap_environment",
                return_value={"venv_python": "conda://ov_env/python"},
            ):
                workspace, _, _ = prepare_workspace(
                    video_dir=video_file,
                    user_request="做一个30秒的会议总结vlog",
                )

            manifest = json.loads((workspace / "runtime_env.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(manifest["workspace_root"]), workspace_root)
            self.assertEqual(manifest["video_count"], 1)
            self.assertEqual(manifest["videos"], [str(video_file)])
            self.assertEqual(manifest["artifact_base_name"], "clip01")
            self.assertTrue((workspace / build_brief_file_name("clip01")).exists())

    def test_analyze_resolve_video_input_supports_directory_and_single_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video_file = root / "meeting.mp4"
            video_file.write_bytes(b"fake-video")

            resolved_root, resolved_videos = analyze_video.resolve_video_input(root)
            self.assertEqual(resolved_root, root)
            self.assertEqual(resolved_videos, [video_file])

            resolved_single_root, resolved_single_videos = analyze_video.resolve_video_input(video_file)
            self.assertEqual(resolved_single_root, root)
            self.assertEqual(resolved_single_videos, [video_file])

    def test_analyze_resolve_output_path_uses_video_name_related_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "editing_20260511_120000"
            workspace.mkdir()
            video_file = root / "meeting.mp4"
            video_file.write_bytes(b"fake-video")
            brief_path = workspace / build_brief_file_name("meeting")
            brief_path.write_text("{}", encoding="utf-8")

            output_path = analyze_video.resolve_output_path(None, root, [video_file], brief_path)

            self.assertEqual(output_path, workspace / build_analysis_file_name("meeting"))

    def test_analyze_resolve_prompt_finds_named_brief_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "editing_20260511_120000"
            workspace.mkdir()
            video_file = root / "meeting.mp4"
            video_file.write_bytes(b"fake-video")
            brief = create_creative_brief("做一个30秒的视频总结vlog，主题：大会回顾，氛围：专业克制")
            brief_path = save_creative_brief(workspace, brief, build_brief_file_name("meeting"))

            prompt, discovered_brief_path = analyze_video.resolve_prompt(None, workspace, None)

            self.assertEqual(discovered_brief_path, brief_path)
            self.assertIn("大会回顾", prompt)

    def test_storyboard_resolve_analysis_input_supports_file_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis_path = root / build_analysis_file_name("meeting")
            analysis_path.write_text("{}", encoding="utf-8")

            self.assertEqual(resolve_analysis_input(analysis_path), analysis_path)
            self.assertEqual(resolve_analysis_input(root), analysis_path)

    def test_storyboard_resolve_output_path_uses_analysis_base_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis_path = root / build_analysis_file_name("meeting")
            analysis_path.write_text("{}", encoding="utf-8")

            output_path = resolve_storyboard_output_path(None, analysis_path)

            self.assertEqual(output_path, root / build_storyboard_file_name("meeting"))

    def test_compose_resolve_storyboard_input_supports_file_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storyboard_path = root / build_storyboard_file_name("meeting")
            storyboard_path.write_text("{}", encoding="utf-8")

            self.assertEqual(resolve_storyboard_input(storyboard_path), storyboard_path)
            self.assertEqual(resolve_storyboard_input(root), storyboard_path)

    def test_cli_prepare_forwards_only_subcommand_args(self) -> None:
        original_argv = sys.argv[:]
        try:
            sys.argv = [
                "run.py",
                "prepare",
                "--video-dir",
                r"C:\videos",
                "--user-request",
                "做一个30秒的视频总结vlog",
            ]
            captured = {}

            def fake_prepare_main() -> int:
                captured["argv"] = sys.argv[:]
                return 0

            with patch("ov_video_editing_skills.cli.prepare_main", side_effect=fake_prepare_main):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                captured["argv"],
                [
                    "run.py",
                    "--video-dir",
                    r"C:\videos",
                    "--user-request",
                    "做一个30秒的视频总结vlog",
                ],
            )
        finally:
            sys.argv = original_argv

    def test_runtime_summary_uses_current_python_not_venv(self) -> None:
        with patch.dict("os.environ", {"CONDA_DEFAULT_ENV": "ov_env"}, clear=False):
            summary = runtime_summary()

        self.assertIn("python_executable", summary)
        self.assertEqual(summary["conda_env_name"], "ov_env")
        self.assertNotIn("venv_dir", summary)
        self.assertNotIn("venv_python", summary)

    def test_bootstrap_environment_only_checks_existing_assets(self) -> None:
        with patch("ov_video_editing_skills.bootstrap.ensure_local_requirements") as ensure_requirements, patch(
            "ov_video_editing_skills.bootstrap.ensure_ffmpeg"
        ) as ensure_ffmpeg, patch("ov_video_editing_skills.bootstrap.ensure_model") as ensure_model, patch(
            "ov_video_editing_skills.bootstrap.runtime_summary",
            return_value={"python_executable": "C:/Python312/python.exe", "conda_env_name": "ov_env"},
        ):
            summary = bootstrap_environment()

        ensure_requirements.assert_called_once_with(force=False)
        ensure_ffmpeg.assert_called_once_with(force=False)
        ensure_model.assert_called_once_with(force=False)
        self.assertEqual(summary["conda_env_name"], "ov_env")


if __name__ == "__main__":
    unittest.main()
