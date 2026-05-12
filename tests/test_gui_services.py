from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ov_video_editing_skills.gui import launcher
from ov_video_editing_skills.gui.models import AppState, TaskConfig, TaskName
from ov_video_editing_skills.gui.services import (
    GuiTaskService,
    build_analyze_args,
    build_compose_args,
    build_e2e_args,
    build_prepare_args,
    build_storyboard_args,
)
from ov_video_editing_skills.gui.settings import load_task_config, save_task_config


class GuiServicesTests(unittest.TestCase):
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