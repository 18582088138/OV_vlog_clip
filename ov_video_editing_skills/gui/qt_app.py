from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import AppState, TaskConfig, TaskName, TaskStatus
from .services import GuiTaskService
from .settings import default_settings_path, load_task_config, save_task_config


class TaskWorker(QThread):
    log_message = Signal(str)
    task_finished = Signal(object)
    task_failed = Signal(str)

    def __init__(self, service: GuiTaskService, task_name: TaskName, config: TaskConfig) -> None:
        super().__init__()
        self.service = service
        self.task_name = task_name
        self.config = config

    def run(self) -> None:
        try:
            result = self.service.run(self.task_name, self.config, self.log_message.emit)
        except Exception as exc:
            self.task_failed.emit(str(exc))
            return
        self.task_finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, settings_path: str | None = None) -> None:
        super().__init__()
        self.settings_path = Path(settings_path).resolve() if settings_path else default_settings_path()
        self.state = AppState(config=load_task_config(self.settings_path))
        self.service = GuiTaskService(self.state)
        self.worker: TaskWorker | None = None

        self.setWindowTitle("OV Video Editing Skills GUI")
        self.resize(1200, 760)
        self._build_ui()
        self._load_config_into_form(self.state.config)
        self._append_log(f"[gui] 已加载配置：{self.settings_path}")

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        left_layout.addWidget(self._build_config_group())
        left_layout.addWidget(self._build_action_group())
        left_layout.addStretch(1)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addWidget(self._build_status_group())
        right_layout.addWidget(self._build_log_group(), stretch=1)

        root_layout.addWidget(left_panel, 5)
        root_layout.addWidget(right_panel, 6)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("就绪")
        self._build_menu()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")

        save_action = QAction("保存配置", self)
        save_action.triggered.connect(self._save_config)
        file_menu.addAction(save_action)

        open_workspace_action = QAction("打开工作区", self)
        open_workspace_action.triggered.connect(self._open_workspace)
        file_menu.addAction(open_workspace_action)

    def _build_config_group(self) -> QGroupBox:
        group = QGroupBox("任务配置", self)
        layout = QFormLayout(group)

        self.video_input_edit = QLineEdit(self)
        self.user_request_edit = QTextEdit(self)
        self.user_request_edit.setFixedHeight(88)
        self.output_dir_edit = QLineEdit(self)
        self.model_dir_edit = QLineEdit(self)
        self.ffmpeg_path_edit = QLineEdit(self)
        self.font_file_edit = QLineEdit(self)
        self.bgm_file_edit = QLineEdit(self)
        self.bgm_style_edit = QLineEdit(self)
        self.brief_path_edit = QLineEdit(self)
        self.analysis_path_edit = QLineEdit(self)
        self.storyboard_path_edit = QLineEdit(self)
        self.device_edit = QLineEdit(self)
        self.device_edit.setPlaceholderText("GPU 或 CPU")

        self.ignore_existing_checkbox = QCheckBox("忽略已有分析结果", self)
        self.skip_ffmpeg_checkbox = QCheckBox("跳过 ffmpeg 检查", self)
        self.skip_model_checkbox = QCheckBox("跳过模型检查", self)

        layout.addRow("视频输入", self._with_browse(self.video_input_edit, self._choose_video_input))
        layout.addRow("用户请求", self.user_request_edit)
        layout.addRow("输出目录", self._with_browse(self.output_dir_edit, self._choose_output_dir))
        layout.addRow("模型目录", self._with_browse(self.model_dir_edit, self._choose_model_dir))
        layout.addRow("ffmpeg 路径", self._with_browse(self.ffmpeg_path_edit, self._choose_ffmpeg_path))
        layout.addRow("字体文件", self._with_browse(self.font_file_edit, self._choose_font_file))
        layout.addRow("BGM 文件", self._with_browse(self.bgm_file_edit, self._choose_bgm_file))
        layout.addRow("BGM 风格", self.bgm_style_edit)
        layout.addRow("Brief 路径", self._with_browse(self.brief_path_edit, self._choose_brief_file))
        layout.addRow("Analysis 路径", self._with_browse(self.analysis_path_edit, self._choose_analysis_file))
        layout.addRow("Storyboard 路径", self._with_browse(self.storyboard_path_edit, self._choose_storyboard_file))
        layout.addRow("推理设备", self.device_edit)
        layout.addRow("", self.ignore_existing_checkbox)
        layout.addRow("", self.skip_ffmpeg_checkbox)
        layout.addRow("", self.skip_model_checkbox)
        return group

    def _build_action_group(self) -> QGroupBox:
        group = QGroupBox("执行操作", self)
        layout = QGridLayout(group)

        self.prepare_button = QPushButton("Prepare", self)
        self.analyze_button = QPushButton("Analyze", self)
        self.storyboard_button = QPushButton("Storyboard", self)
        self.compose_button = QPushButton("Compose", self)
        self.e2e_button = QPushButton("E2E", self)
        self.save_button = QPushButton("保存配置", self)

        self.prepare_button.clicked.connect(lambda: self._start_task(TaskName.PREPARE))
        self.analyze_button.clicked.connect(lambda: self._start_task(TaskName.ANALYZE))
        self.storyboard_button.clicked.connect(lambda: self._start_task(TaskName.STORYBOARD))
        self.compose_button.clicked.connect(lambda: self._start_task(TaskName.COMPOSE))
        self.e2e_button.clicked.connect(lambda: self._start_task(TaskName.E2E))
        self.save_button.clicked.connect(self._save_config)

        layout.addWidget(self.prepare_button, 0, 0)
        layout.addWidget(self.analyze_button, 0, 1)
        layout.addWidget(self.storyboard_button, 1, 0)
        layout.addWidget(self.compose_button, 1, 1)
        layout.addWidget(self.e2e_button, 2, 0)
        layout.addWidget(self.save_button, 2, 1)
        return group

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("当前状态", self)
        layout = QVBoxLayout(group)
        self.status_label = QLabel("状态：idle", self)
        self.workspace_label = QLabel("工作区：", self)
        self.workspace_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.workspace_label)
        return group

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("日志输出", self)
        layout = QVBoxLayout(group)
        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log_view)
        return group

    def _with_browse(self, edit: QLineEdit, handler) -> QWidget:
        wrapper = QWidget(self)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        browse_button = QPushButton("浏览", self)
        browse_button.clicked.connect(handler)
        layout.addWidget(edit)
        layout.addWidget(browse_button)
        return wrapper

    def _collect_config(self) -> TaskConfig:
        return TaskConfig(
            video_input=self.video_input_edit.text().strip(),
            user_request=self.user_request_edit.toPlainText().strip(),
            output_dir=self.output_dir_edit.text().strip(),
            model_dir=self.model_dir_edit.text().strip(),
            ffmpeg_path=self.ffmpeg_path_edit.text().strip(),
            font_file=self.font_file_edit.text().strip(),
            bgm_file=self.bgm_file_edit.text().strip(),
            bgm_style=self.bgm_style_edit.text().strip(),
            brief_path=self.brief_path_edit.text().strip(),
            analysis_path=self.analysis_path_edit.text().strip(),
            storyboard_path=self.storyboard_path_edit.text().strip(),
            device=self.device_edit.text().strip() or "GPU",
            ignore_existing_analysis=self.ignore_existing_checkbox.isChecked(),
            skip_ffmpeg=self.skip_ffmpeg_checkbox.isChecked(),
            skip_model=self.skip_model_checkbox.isChecked(),
        )

    def _load_config_into_form(self, config: TaskConfig) -> None:
        self.video_input_edit.setText(config.video_input)
        self.user_request_edit.setPlainText(config.user_request)
        self.output_dir_edit.setText(config.output_dir)
        self.model_dir_edit.setText(config.model_dir)
        self.ffmpeg_path_edit.setText(config.ffmpeg_path)
        self.font_file_edit.setText(config.font_file)
        self.bgm_file_edit.setText(config.bgm_file)
        self.bgm_style_edit.setText(config.bgm_style)
        self.brief_path_edit.setText(config.brief_path)
        self.analysis_path_edit.setText(config.analysis_path)
        self.storyboard_path_edit.setText(config.storyboard_path)
        self.device_edit.setText(config.device)
        self.ignore_existing_checkbox.setChecked(config.ignore_existing_analysis)
        self.skip_ffmpeg_checkbox.setChecked(config.skip_ffmpeg)
        self.skip_model_checkbox.setChecked(config.skip_model)

    def _append_log(self, text: str) -> None:
        normalized = str(text).rstrip("\n")
        if not normalized:
            return
        self.state.append_log(normalized)
        self.log_view.appendPlainText(normalized)

    def _refresh_status(self) -> None:
        self.status_label.setText(f"状态：{self.state.status.value}")
        self.workspace_label.setText(f"工作区：{self.state.workspace_dir}")
        self.statusBar().showMessage(f"当前状态：{self.state.status.value}")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in [
            self.prepare_button,
            self.analyze_button,
            self.storyboard_button,
            self.compose_button,
            self.e2e_button,
            self.save_button,
        ]:
            button.setEnabled(enabled)

    def _save_config(self) -> None:
        self.state.config = self._collect_config()
        save_task_config(self.state.config, self.settings_path)
        self._append_log(f"[gui] 配置已保存：{self.settings_path}")
        self.statusBar().showMessage("配置已保存", 3000)

    def _start_task(self, task_name: TaskName) -> None:
        config = self._collect_config()
        self.state.config = config
        self._save_config()
        self._set_buttons_enabled(False)
        self.state.status = TaskStatus.RUNNING
        self._refresh_status()

        self.worker = TaskWorker(self.service, task_name, config)
        self.worker.log_message.connect(self._append_log)
        self.worker.task_finished.connect(self._handle_task_finished)
        self.worker.task_failed.connect(self._handle_task_failed)
        self.worker.start()

    def _handle_task_finished(self, result) -> None:
        self._set_buttons_enabled(True)
        self.state.last_result = result
        self._refresh_status()
        if result.succeeded:
            self._append_log(f"[gui] 任务成功：{result.task_name.value}")
        else:
            self._append_log(f"[gui] 任务失败：{result.task_name.value}")
            QMessageBox.warning(self, "任务失败", result.stderr or result.stdout or "任务执行失败")
        self._refresh_form_from_state()

    def _handle_task_failed(self, message: str) -> None:
        self._set_buttons_enabled(True)
        self.state.status = TaskStatus.FAILED
        self._refresh_status()
        self._append_log(f"[gui] 异常：{message}")
        QMessageBox.critical(self, "执行异常", message)

    def _refresh_form_from_state(self) -> None:
        if self.state.workspace_dir and not self.output_dir_edit.text().strip():
            self.output_dir_edit.setText(self.state.workspace_dir)
        if self.state.artifact_paths:
            if not self.brief_path_edit.text().strip():
                self.brief_path_edit.setText(self.state.artifact_paths.get("brief", ""))
            if not self.analysis_path_edit.text().strip():
                self.analysis_path_edit.setText(self.state.artifact_paths.get("analysis", ""))
            if not self.storyboard_path_edit.text().strip():
                self.storyboard_path_edit.setText(self.state.artifact_paths.get("storyboard", ""))

    def _open_workspace(self) -> None:
        if not self.state.workspace_dir:
            QMessageBox.information(self, "提示", "当前还没有可打开的工作区。")
            return
        path = Path(self.state.workspace_dir)
        if not path.exists():
            QMessageBox.warning(self, "提示", f"工作区不存在：{path}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "提示", f"无法打开工作区：{path}")

    def _choose_video_input(self) -> None:
        self._choose_path_for_edit(self.video_input_edit, file_or_dir=True)

    def _choose_output_dir(self) -> None:
        self._choose_directory_for_edit(self.output_dir_edit)

    def _choose_model_dir(self) -> None:
        self._choose_directory_for_edit(self.model_dir_edit)

    def _choose_ffmpeg_path(self) -> None:
        self._choose_file_for_edit(self.ffmpeg_path_edit, "选择 ffmpeg", "可执行文件 (*.exe);;所有文件 (*)")

    def _choose_font_file(self) -> None:
        self._choose_file_for_edit(self.font_file_edit, "选择字体文件", "字体文件 (*.ttf *.otf *.ttc);;所有文件 (*)")

    def _choose_bgm_file(self) -> None:
        self._choose_file_for_edit(self.bgm_file_edit, "选择 BGM 文件", "音频文件 (*.mp3 *.wav *.flac);;所有文件 (*)")

    def _choose_brief_file(self) -> None:
        self._choose_file_for_edit(self.brief_path_edit, "选择 Brief 文件", "JSON 文件 (*.json);;所有文件 (*)")

    def _choose_analysis_file(self) -> None:
        self._choose_file_for_edit(self.analysis_path_edit, "选择 Analysis 文件", "JSON 文件 (*.json);;所有文件 (*)")

    def _choose_storyboard_file(self) -> None:
        self._choose_file_for_edit(self.storyboard_path_edit, "选择 Storyboard 文件", "JSON 文件 (*.json);;所有文件 (*)")

    def _choose_path_for_edit(self, edit: QLineEdit, file_or_dir: bool = False) -> None:
        current = edit.text().strip()
        if file_or_dir:
            file_path, _ = QFileDialog.getOpenFileName(self, "选择视频文件", current or "", "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv);;所有文件 (*)")
            if file_path:
                edit.setText(file_path)
                return
            directory = QFileDialog.getExistingDirectory(self, "选择视频目录", current or "")
            if directory:
                edit.setText(directory)

    def _choose_directory_for_edit(self, edit: QLineEdit) -> None:
        current = edit.text().strip()
        directory = QFileDialog.getExistingDirectory(self, "选择目录", current or "")
        if directory:
            edit.setText(directory)

    def _choose_file_for_edit(self, edit: QLineEdit, title: str, file_filter: str) -> None:
        current = edit.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(self, title, current or "", file_filter)
        if file_path:
            edit.setText(file_path)


def run_gui(settings_path: str | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=settings_path)
    window.show()
    return int(app.exec())