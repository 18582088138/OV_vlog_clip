from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ov_video_editing_skills.gui import launcher
from ov_video_editing_skills.gui.models import AppState, TaskConfig, TaskName
from ov_video_editing_skills.gui.services import (
    GuiTaskService,
    build_artifact_preview,
    build_analyze_args,
    build_compose_args,
    build_e2e_args,
    build_prepare_args,
    build_storyboard_args,
    collect_workspace_artifacts,
    extract_final_video_path,
)
from ov_video_editing_skills.gui.models import WorkspaceArtifact
from ov_video_editing_skills.gui.settings import load_default_task_config, load_task_config, save_task_config
from ov_video_editing_skills.runtime import DEFAULT_MODEL_DIR


class GuiServicesTests(unittest.TestCase):
    def test_load_default_task_config_uses_package_defaults(self) -> None:
        config = load_default_task_config()

        self.assertEqual(config.device, "GPU")
        self.assertEqual(config.model_dir, str(DEFAULT_MODEL_DIR))

    def test_load_default_task_config_supports_custom_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "custom_gui_config.json"
            config_path.write_text(
                '{"device": "CPU", "model_dir": "D:/models/custom", "user_request": "临时请求"}',
                encoding="utf-8",
            )
            config = load_default_task_config(config_path)

        self.assertEqual(config.device, "CPU")
        self.assertEqual(config.model_dir, "D:/models/custom")
        self.assertEqual(config.user_request, "临时请求")

    def test_save_and_load_task_config_roundtrip(self) -> None:
        config = TaskConfig(
            video_input=r"D:\videos\input.mp4",
            user_request="做一个 30 秒总结视频",
            output_dir=r"D:\videos\output",
            model_dir=r"D:\models\qwen",
            ffmpeg_path=r"D:\ffmpeg\bin\ffmpeg.exe",
            device="CPU",
            skip_ffmpeg=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "gui-settings.json"
            save_task_config(config, settings_path)
            loaded = load_task_config(settings_path)

        self.assertEqual(loaded.video_input, config.video_input)
        self.assertEqual(loaded.user_request, config.user_request)
        self.assertEqual(loaded.output_dir, config.output_dir)
        self.assertEqual(loaded.model_dir, config.model_dir)
        self.assertEqual(loaded.ffmpeg_path, config.ffmpeg_path)
        self.assertEqual(loaded.device, "CPU")
        self.assertTrue(loaded.skip_ffmpeg)

    def test_build_prepare_args_includes_skip_flags(self) -> None:
        config = TaskConfig(
            video_input=r"D:\videos\input.mp4",
            user_request="做一个总结",
            ignore_existing_analysis=True,
            skip_ffmpeg=True,
            skip_model=True,
        )

        args = build_prepare_args(config)

        self.assertIn("--video-dir", args)
        self.assertIn("--ignore-existing-analysis", args)
        self.assertIn("--skip-ffmpeg", args)
        self.assertIn("--skip-model", args)

    def test_build_followup_args_uses_workspace_artifacts(self) -> None:
        state = AppState(workspace_dir=r"D:\videos\editing_20260512_120000")
        state.artifact_paths = {
            "brief": r"D:\videos\editing_20260512_120000\input_brief.json",
            "analysis": r"D:\videos\editing_20260512_120000\input_output_vlm.json",
            "storyboard": r"D:\videos\editing_20260512_120000\input_storyboard.json",
        }
        config = TaskConfig(
            video_input=r"D:\videos\input.mp4",
            output_dir=r"D:\videos\final_output",
            model_dir=r"D:\models\qwen",
            ffmpeg_path=r"D:\ffmpeg\bin\ffmpeg.exe",
            bgm_file=r"D:\bgm\theme.mp3",
            bgm_style="warm",
            device="CPU",
        )

        analyze_args = build_analyze_args(config, state)
        storyboard_args = build_storyboard_args(config, state)
        compose_args = build_compose_args(config, state)

        self.assertIn(r"D:\videos\editing_20260512_120000\input_brief.json", analyze_args)
        self.assertIn(r"D:\videos\editing_20260512_120000\input_output_vlm.json", storyboard_args)
        self.assertIn(r"D:\videos\editing_20260512_120000\input_storyboard.json", compose_args)
        self.assertIn(r"D:\ffmpeg\bin\ffmpeg.exe", compose_args)

    def test_build_e2e_args_forwards_optional_paths(self) -> None:
        config = TaskConfig(
            video_input=r"D:\videos\input.mp4",
            user_request="做一个 vlog",
            output_dir=r"D:\videos\output",
            model_dir=r"D:\models\qwen",
            ffmpeg_path=r"D:\ffmpeg\bin\ffmpeg.exe",
            font_file=r"D:\fonts\msyh.ttc",
            bgm_file=r"D:\bgm\theme.mp3",
            bgm_style="calm",
            device="CPU",
            ignore_existing_analysis=True,
            skip_ffmpeg=True,
            skip_model=True,
        )

        args = build_e2e_args(config)

        self.assertIn("--model-dir", args)
        self.assertIn("--ffmpeg", args)
        self.assertIn("--font-file", args)
        self.assertIn("--bgm-file", args)
        self.assertIn("--bgm-style", args)
        self.assertIn("--ignore-existing-analysis", args)
        self.assertIn("--skip-ffmpeg", args)
        self.assertIn("--skip-model", args)

    def test_extract_final_video_path_from_compose_output(self) -> None:
        final_path = extract_final_video_path("Done. Final output: D:/videos/out/final.mp4\n")

        self.assertIsNotNone(final_path)
        self.assertEqual(str(final_path).replace('\\', '/'), "D:/videos/out/final.mp4")

    def test_collect_workspace_artifacts_includes_core_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "user_input.txt").write_text("做一个总结", encoding="utf-8")
            (workspace / "runtime_env.json").write_text('{"python": "3.11"}', encoding="utf-8")
            brief = workspace / "sample_brief.json"
            analysis = workspace / "sample_output_vlm.json"
            storyboard = workspace / "sample_storyboard.json"
            brief.write_text('{"theme": "demo"}', encoding="utf-8")
            analysis.write_text('{"segments": []}', encoding="utf-8")
            storyboard.write_text('{"clips": [{"subtitle": "hello"}], "story_outline": {"theme": "demo"}}', encoding="utf-8")

            state = AppState(workspace_dir=str(workspace))
            state.artifact_paths = {
                "brief": str(brief),
                "analysis": str(analysis),
                "storyboard": str(storyboard),
            }

            artifacts = collect_workspace_artifacts(state, TaskConfig(video_input=str(workspace)))

        by_key = {artifact.key: artifact for artifact in artifacts}
        self.assertTrue(by_key["user_input"].exists)
        self.assertTrue(by_key["brief"].exists)
        self.assertTrue(by_key["analysis"].exists)
        self.assertTrue(by_key["storyboard"].exists)
        self.assertTrue(by_key["runtime"].exists)

    def test_build_artifact_preview_summarizes_storyboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storyboard_path = Path(temp_dir) / "sample_storyboard.json"
            storyboard_path.write_text(
                '{"story_outline": {"theme": "科技", "emotional_arc": "起承转合", "must_capture": ["演讲", "观众"]}, "clips": [{"start": 0, "end": 5, "subtitle": "开场", "narrative_role": "opening", "transition": "fade"}]}',
                encoding="utf-8",
            )
            artifact = WorkspaceArtifact(
                key="storyboard",
                label="Storyboard",
                path=str(storyboard_path),
                exists=True,
                description="分镜结果",
            )

            preview = build_artifact_preview(artifact)

        self.assertIn("[Storyboard 结构预览]", preview)
        self.assertIn("分镜数量：1", preview)
        self.assertIn("开场", preview)

    def test_launcher_reports_missing_pyside6(self) -> None:
        with mock.patch("importlib.import_module", side_effect=ModuleNotFoundError("No module named 'PySide6'")):
            result = launcher.main([])

        self.assertEqual(result, 1)

    def test_service_rejects_empty_video_input(self) -> None:
        state = AppState()
        service = GuiTaskService(state)

        with self.assertRaises(ValueError):
            service.run(TaskName.PREPARE, TaskConfig(video_input=""))


if __name__ == "__main__":
    unittest.main()