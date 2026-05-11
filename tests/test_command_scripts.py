from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CommandScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.prepare_script = load_module("test_prepare_script", cls.repo_root / "scripts" / "test_prepare.py")
        cls.analyze_script = load_module("test_analyze_script", cls.repo_root / "scripts" / "test_analyze.py")
        cls.storyboard_script = load_module("test_storyboard_script", cls.repo_root / "scripts" / "test_storyboard.py")
        cls.compose_script = load_module("test_compose_script", cls.repo_root / "scripts" / "test_compose.py")
        cls.e2e_script = load_module("test_e2e_script", cls.repo_root / "scripts" / "test_e2e.py")

    def test_prepare_command_uses_default_request_and_extra_args(self) -> None:
        command = self.prepare_script.build_prepare_command(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos" / "2022yunqidahui.mp4",
            extra_args=["--skip-model"],
        )

        self.assertEqual(command[:4], ["python", "run.py", "prepare", "--video-dir"])
        self.assertIn("做一个30秒的视频总结vlog", command)
        self.assertEqual(command[-1], "--skip-model")

    def test_prepare_command_can_forward_ignore_flag(self) -> None:
        command = self.prepare_script.build_prepare_command(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos",
            ignore_existing_analysis=True,
        )

        self.assertIn("--ignore-existing-analysis", command)

    def test_analyze_command_supports_optional_brief_and_output(self) -> None:
        command = self.analyze_script.build_analyze_command(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos" / "2022yunqidahui.mp4",
            brief=self.repo_root / "videos" / "editing_20260511_120000" / "2022yunqidahui_brief.json",
            output=self.repo_root / "videos" / "editing_20260511_120000" / "2022yunqidahui_output_vlm.json",
            extra_args=["--device", "CPU"],
        )

        self.assertEqual(command[:4], ["python", "run.py", "analyze", "--video-dir"])
        self.assertIn("--brief", command)
        self.assertIn("--output", command)
        self.assertEqual(command[-2:], ["--device", "CPU"])

    def test_default_video_input_prefers_single_video_file(self) -> None:
        default_path = self.analyze_script.default_video_input(self.repo_root)
        self.assertTrue(default_path.exists())
        self.assertIn(default_path.name, {"2022yunqidahui.mp4", "videos"})

    def test_storyboard_command_supports_directory_input_and_extra_args(self) -> None:
        command = self.storyboard_script.build_storyboard_command(
            repo_root=self.repo_root,
            python_executable="python",
            analysis=self.repo_root / "videos",
            extra_args=["--target-duration", "30"],
        )

        self.assertEqual(command[:4], ["python", "run.py", "storyboard", "--analysis"])
        self.assertEqual(command[-2:], ["--target-duration", "30"])

    def test_storyboard_command_supports_file_input_and_optional_paths(self) -> None:
        command = self.storyboard_script.build_storyboard_command(
            repo_root=self.repo_root,
            python_executable="python",
            analysis=self.repo_root / "videos" / "2022yunqidahui_output_vlm.json",
            output=self.repo_root / "videos" / "2022yunqidahui_storyboard.json",
            brief=self.repo_root / "videos" / "2022yunqidahui_brief.json",
        )

        self.assertIn("--output", command)
        self.assertIn("--brief", command)

    def test_compose_command_supports_directory_input_and_output_dir(self) -> None:
        command = self.compose_script.build_compose_command(
            repo_root=self.repo_root,
            python_executable="python",
            storyboard=self.repo_root / "videos",
            output_dir=self.repo_root / "videos" / "final_output",
            extra_args=["--dry-run"],
        )

        self.assertEqual(command[:4], ["python", "run.py", "compose", "--storyboard"])
        self.assertIn("--output-dir", command)
        self.assertEqual(command[-1], "--dry-run")

    def test_compose_default_storyboard_input_prefers_directory(self) -> None:
        default_path = self.compose_script.default_storyboard_input(self.repo_root)
        self.assertTrue(default_path.exists())
        self.assertIn(default_path.name, {"videos", "2022yunqidahui_storyboard.json", "storyboard.json"})

    def test_e2e_builds_full_command_chain_for_single_video(self) -> None:
        commands = self.e2e_script.build_e2e_commands(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos" / "2022yunqidahui.mp4",
            user_request="做一个30秒的视频总结vlog",
        )

        self.assertEqual(commands["prepare"][:4], ["python", "run.py", "prepare", "--video-dir"])
        self.assertEqual(commands["analyze"][:4], ["python", "run.py", "analyze", "--video-dir"])
        self.assertEqual(commands["storyboard"][:4], ["python", "run.py", "storyboard", "--analysis"])
        self.assertEqual(commands["compose"][:4], ["python", "run.py", "compose", "--storyboard"])
        self.assertTrue(commands["paths"]["brief"].endswith("2022yunqidahui_brief.json"))
        self.assertTrue(commands["paths"]["analysis"].endswith("2022yunqidahui_output_vlm.json"))
        self.assertTrue(commands["paths"]["storyboard"].endswith("2022yunqidahui_storyboard.json"))

    def test_e2e_builds_full_command_chain_for_directory(self) -> None:
        commands = self.e2e_script.build_e2e_commands(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos",
            ignore_existing_analysis=True,
            output_dir=self.repo_root / "videos" / "final_output",
        )

        self.assertIn("--ignore-existing-analysis", commands["prepare"])
        self.assertIn("--output-dir", commands["compose"])
        self.assertTrue(commands["paths"]["brief"].endswith("videos_brief.json"))
        self.assertTrue(commands["paths"]["analysis"].endswith("videos_output_vlm.json"))
        self.assertTrue(commands["paths"]["storyboard"].endswith("videos_storyboard.json"))

    def test_e2e_extract_workspace_from_prepare_output_supports_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "editing_20260511_120000"
            workspace.mkdir()

            result = self.e2e_script.extract_workspace_from_prepare_output(
                stdout=f"[准备] 工作区已创建\n{workspace}\n",
                stderr=None,
            )

            self.assertEqual(result, workspace.resolve())

    def test_e2e_extract_workspace_from_prepare_output_supports_stderr_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "editing_20260511_120001"
            workspace.mkdir()

            result = self.e2e_script.extract_workspace_from_prepare_output(
                stdout=None,
                stderr=f"warning\n{workspace}\n",
            )

            self.assertEqual(result, workspace.resolve())


if __name__ == "__main__":
    unittest.main()
