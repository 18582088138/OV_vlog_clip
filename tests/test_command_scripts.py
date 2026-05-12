from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from ov_video_editing_skills import cli as package_cli
from ov_video_editing_skills import e2e as package_e2e
from ov_video_editing_skills.gui import launcher as gui_launcher


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

    def test_e2e_can_forward_skip_checks_for_portable_exe(self) -> None:
        commands = self.e2e_script.build_e2e_commands(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos",
            skip_ffmpeg=True,
            skip_model=True,
        )

        self.assertIn("--skip-ffmpeg", commands["prepare"])
        self.assertIn("--skip-model", commands["prepare"])

    def test_e2e_can_forward_external_model_bgm_and_ffmpeg_paths(self) -> None:
        commands = self.e2e_script.build_e2e_commands(
            repo_root=self.repo_root,
            python_executable="python",
            video_dir=self.repo_root / "videos" / "2022yunqidahui.mp4",
            analyze_extra_args=["--model-dir", r"D:\models\Qwen", "--device", "CPU"],
            storyboard_extra_args=["--bgm-file", r"D:\bgm\theme.mp3"],
            compose_extra_args=["--ffmpeg", r"D:\ffmpeg\bin\ffmpeg.exe"],
        )

        self.assertEqual(commands["analyze"][-4:], ["--model-dir", r"D:\models\Qwen", "--device", "CPU"])
        self.assertEqual(commands["storyboard"][-2:], ["--bgm-file", r"D:\bgm\theme.mp3"])
        self.assertEqual(commands["compose"][-2:], ["--ffmpeg", r"D:\ffmpeg\bin\ffmpeg.exe"])

    def test_main_cli_exposes_e2e_subcommand(self) -> None:
        parser = package_cli.build_parser()
        args = parser.parse_args(["e2e"])

        self.assertEqual(args.command, "e2e")

    def test_main_cli_exposes_gui_subcommand(self) -> None:
        parser = package_cli.build_parser()
        args = parser.parse_args(["gui"])

        self.assertEqual(args.command, "gui")

    def test_package_e2e_default_video_input_prefers_repo_fixture(self) -> None:
        default_path = package_e2e.default_video_input(self.repo_root)

        self.assertTrue(default_path.exists())
        self.assertIn(default_path.name, {"2022yunqidahui.mp4", "videos"})

    def test_pyproject_declares_portable_console_scripts(self) -> None:
        pyproject_path = self.repo_root / "pyproject.toml"
        content = pyproject_path.read_text(encoding="utf-8")

        self.assertIn('ov-video-editing-skills = "ov_video_editing_skills.cli:main"', content)
        self.assertIn('ov-video-editing-e2e = "ov_video_editing_skills.e2e:main"', content)
        self.assertIn('ov-video-editing-gui = "ov_video_editing_skills.gui.launcher:main"', content)

    def test_gui_pyinstaller_assets_exist(self) -> None:
        gui_entry = self.repo_root / "gui_entry.py"
        gui_spec = self.repo_root / "ov_video_editing_gui.spec"
        gui_build_script = self.repo_root / "build_gui_exe.cmd"

        self.assertTrue(gui_entry.exists())
        self.assertTrue(gui_spec.exists())
        self.assertTrue(gui_build_script.exists())

        self.assertIn("ov_video_editing_skills.gui.launcher", gui_entry.read_text(encoding="utf-8"))
        gui_spec_content = gui_spec.read_text(encoding="utf-8")
        self.assertIn('name="ov-video-editing-gui"', gui_spec_content)
        self.assertIn("sys.path.insert(0, str(project_root))", gui_spec_content)
        self.assertIn('"ov_video_editing_skills.gui.qt_app"', gui_spec_content)
        self.assertIn("ov_video_editing_gui.spec", gui_build_script.read_text(encoding="utf-8"))

    def test_gui_launcher_parser_supports_settings_path(self) -> None:
        args = gui_launcher.build_parser().parse_args(["--settings", "custom.json"])

        self.assertEqual(args.settings, "custom.json")

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
