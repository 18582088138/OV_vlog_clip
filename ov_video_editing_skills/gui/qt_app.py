from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal, Qt
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..analyze_video import VIDEO_EXTENSIONS
from .models import AppState, DiagnosticIssue, TaskConfig, TaskName, TaskStatus, WorkspaceArtifact
from .services import GuiTaskService, build_artifact_preview, collect_diagnostic_issues, collect_environment_checks, collect_workspace_artifacts, format_environment_checks
from .settings import describe_default_config_source, load_task_config

INTEL_STYLE_SHEET = """
QMainWindow {
    background: #f3f7fb;
}
QWidget {
    color: #1f2937;
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    font-size: 13px;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #d8e6f2;
    border-radius: 16px;
    margin-top: 12px;
    padding: 14px;
    font-weight: 600;
    color: #004a86;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background: #f9fcff;
    border: 1px solid #c7d8ea;
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid #0068b5;
}
QPushButton {
    background: #0068b5;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background: #00579a;
}
QPushButton:disabled {
    background: #9bb7d0;
}
QPushButton[variant="secondary"] {
    background: #eaf4fb;
    color: #00579a;
    border: 1px solid #bcd5ea;
}
QPushButton[variant="secondary"]:hover {
    background: #dcedf9;
}
QLabel[role="title"] {
    font-size: 24px;
    font-weight: 700;
    color: #00579a;
}
QLabel[role="subtitle"] {
    color: #5b6b7a;
    font-size: 13px;
}
QFrame[card="hero"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0068b5, stop:1 #00a3e0);
    border-radius: 18px;
}
QFrame[card="hero"] QLabel {
    color: white;
}
QLabel[role="muted"] {
    color: #6b7280;
}
QStatusBar {
    background: #eaf4fb;
    color: #004a86;
}
QLabel[severity="error"] {
    background: #fff1f2;
    color: #b42318;
    border: 1px solid #fecdca;
    border-radius: 10px;
    padding: 10px 12px;
}
QLabel[severity="warning"] {
    background: #fffaeb;
    color: #b54708;
    border: 1px solid #fedf89;
    border-radius: 10px;
    padding: 10px 12px;
}
QLabel[severity="info"] {
    background: #eff8ff;
    color: #175cd3;
    border: 1px solid #b2ddff;
    border-radius: 10px;
    padding: 10px 12px;
}
"""


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


class VideoPlayerWidget(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_video: Path | None = None
        self._is_slider_pressed = False
        self._was_playing_before_seek = False
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.65)
        self.player.setAudioOutput(self.audio_output)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title_label = QLabel(title, self)
        self.title_label.setProperty("role", "title")
        self.title_label.setStyleSheet("font-size: 18px;")
        self.path_label = QLabel("当前无可预览视频", self)
        self.path_label.setWordWrap(True)
        self.path_label.setProperty("role", "muted")

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(280)
        self.video_widget.setStyleSheet("background: #0f1720; border-radius: 14px;")
        self.player.setVideoOutput(self.video_widget)

        self.placeholder = QLabel("请选择视频文件或包含视频的目录以启用预览", self)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setMinimumHeight(280)
        self.placeholder.setStyleSheet(
            "background: #0f1720; color: #d7e8f7; border-radius: 14px; padding: 24px;"
        )

        self.play_button = QPushButton("播放 / 暂停", self)
        self.stop_button = QPushButton("停止", self)
        self.open_button = QPushButton("打开所在目录", self)
        self.progress_slider = QSlider(Qt.Horizontal, self)
        self.progress_slider.setRange(0, 0)
        self.position_label = QLabel("00:00 / 00:00", self)
        self.position_label.setProperty("role", "muted")
        for button in [self.stop_button, self.open_button]:
            button.setProperty("variant", "secondary")
            button.style().unpolish(button)
            button.style().polish(button)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.position_label)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.open_button)
        controls.addStretch(1)

        layout.addWidget(self.title_label)
        layout.addWidget(self.path_label)
        layout.addWidget(self.placeholder)
        layout.addWidget(self.video_widget)
        layout.addLayout(progress_layout)
        layout.addLayout(controls)

        self.video_widget.hide()

        self.play_button.clicked.connect(self.toggle_playback)
        self.stop_button.clicked.connect(self.stop)
        self.open_button.clicked.connect(self.open_parent_dir)
        self.progress_slider.sliderPressed.connect(self._handle_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._handle_slider_released)
        self.progress_slider.sliderMoved.connect(self._handle_slider_moved)
        self.player.durationChanged.connect(self._handle_duration_changed)
        self.player.positionChanged.connect(self._handle_position_changed)

    def set_video(self, video_path: Path | None) -> None:
        self.current_video = video_path if video_path and video_path.exists() else None
        self.player.stop()
        self.progress_slider.setValue(0)
        self.progress_slider.setRange(0, 0)
        self.position_label.setText("00:00 / 00:00")
        if self.current_video is None:
            self.path_label.setText("当前无可预览视频")
            self.video_widget.hide()
            self.placeholder.show()
            return

        self.path_label.setText(str(self.current_video))
        self.placeholder.hide()
        self.video_widget.show()
        self.player.setSource(QUrl.fromLocalFile(str(self.current_video)))

    def toggle_playback(self) -> None:
        if self.current_video is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self) -> None:
        self.player.stop()
        # 重置进度与时间显示到起始位置
        try:
            self.progress_slider.setValue(0)
            self._update_position_label(0, self.player.duration())
        except Exception:
            pass

    def open_parent_dir(self) -> None:
        if self.current_video is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_video.parent)))

    def _handle_duration_changed(self, duration: int) -> None:
        self.progress_slider.setRange(0, max(duration, 0))
        self._update_position_label(self.player.position(), duration)

    def _handle_position_changed(self, position: int) -> None:
        if not self._is_slider_pressed:
            self.progress_slider.setValue(position)
        self._update_position_label(position, self.player.duration())

    def _handle_slider_pressed(self) -> None:
        # 记录按下时播放状态，释放后按此状态决定是否恢复播放
        self._is_slider_pressed = True
        self._was_playing_before_seek = self.player.playbackState() == QMediaPlayer.PlayingState
        if self._was_playing_before_seek:
            # 暂停播放以便用户拖拽
            self.player.pause()

    def _handle_slider_released(self) -> None:
        self._is_slider_pressed = False
        # 跳转到所选位置
        new_pos = self.progress_slider.value()
        self.player.setPosition(new_pos)
        # 若释放前正在播放，则恢复播放
        if self._was_playing_before_seek:
            self.player.play()
        self._was_playing_before_seek = False

    def _handle_slider_moved(self, value: int) -> None:
        self._update_position_label(value, self.player.duration())

    def _update_position_label(self, position: int, duration: int) -> None:
        self.position_label.setText(f"{self._format_ms(position)} / {self._format_ms(duration)}")

    @staticmethod
    def _format_ms(value: int) -> str:
        total_seconds = max(int(value / 1000), 0)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


class ResultVideoDialog(QDialog):
    def __init__(self, video_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("剪辑完成 - 成片预览")
        self.resize(960, 640)

        layout = QVBoxLayout(self)
        summary = QLabel("已生成新的剪辑视频，可直接预览或打开输出目录。", self)
        summary.setProperty("role", "subtitle")
        layout.addWidget(summary)

        self.player_widget = VideoPlayerWidget("成片预览", self)
        self.player_widget.set_video(video_path)
        layout.addWidget(self.player_widget)


class SettingsDialog(QDialog):
    def __init__(self, config: TaskConfig, default_source: str, default_config: TaskConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_config = replace(config)
        self.default_config = replace(default_config)
        self.setWindowTitle("Settings - 临时参数")
        self.resize(720, 560)
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_content = QWidget(self)
        content_layout = QVBoxLayout(scroll_content)

        summary = QLabel(
            f"当前参数默认来自：{default_source}\n通过本窗口修改的参数仅在当前 GUI 会话中生效，不会覆盖 default config。",
            self,
        )
        summary.setWordWrap(True)
        summary.setProperty("role", "subtitle")
        content_layout.addWidget(summary)

        form_group = QGroupBox("临时配置", self)
        form = QFormLayout(form_group)

        self.user_request_edit = QTextEdit(self)
        self.user_request_edit.setFixedHeight(96)
        self.user_request_edit.setPlainText(config.user_request)
        self.output_dir_edit = QLineEdit(config.output_dir, self)
        self.ffmpeg_path_edit = QLineEdit(config.ffmpeg_path, self)
        self.font_file_edit = QLineEdit(config.font_file, self)
        self.bgm_file_edit = QLineEdit(config.bgm_file, self)
        self.bgm_style_edit = QLineEdit(config.bgm_style, self)
        self.brief_path_edit = QLineEdit(config.brief_path, self)
        self.analysis_path_edit = QLineEdit(config.analysis_path, self)
        self.storyboard_path_edit = QLineEdit(config.storyboard_path, self)
        self.log_level_combo = QComboBox(self)
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        log_level_index = self.log_level_combo.findText((config.log_level or "INFO").upper())
        self.log_level_combo.setCurrentIndex(log_level_index if log_level_index >= 0 else 1)

        self.ignore_existing_checkbox = QCheckBox("忽略已有分析结果", self)
        self.skip_ffmpeg_checkbox = QCheckBox("跳过 ffmpeg 检查", self)
        self.skip_model_checkbox = QCheckBox("跳过模型检查", self)
        self.ignore_existing_checkbox.setChecked(config.ignore_existing_analysis)
        self.skip_ffmpeg_checkbox.setChecked(config.skip_ffmpeg)
        self.skip_model_checkbox.setChecked(config.skip_model)

        form.addRow("用户请求", self.user_request_edit)
        form.addRow("输出目录", self._with_browse(self.output_dir_edit, self._choose_output_dir))
        form.addRow("ffmpeg 路径", self._with_browse(self.ffmpeg_path_edit, self._choose_ffmpeg_file))
        form.addRow("字体文件", self._with_browse(self.font_file_edit, self._choose_font_file))
        form.addRow("BGM 文件", self._with_browse(self.bgm_file_edit, self._choose_bgm_file))
        form.addRow("BGM 风格", self.bgm_style_edit)
        form.addRow("Brief 路径", self._with_browse(self.brief_path_edit, self._choose_brief_file))
        form.addRow("Analysis 路径", self._with_browse(self.analysis_path_edit, self._choose_analysis_file))
        form.addRow("Storyboard 路径", self._with_browse(self.storyboard_path_edit, self._choose_storyboard_file))
        form.addRow("日志级别", self.log_level_combo)
        form.addRow("", self.ignore_existing_checkbox)
        form.addRow("", self.skip_ffmpeg_checkbox)
        form.addRow("", self.skip_model_checkbox)

        content_layout.addWidget(form_group)
        content_layout.addStretch(1)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.reset_button = QPushButton("恢复 default config", self)
        self.reset_button.setProperty("variant", "secondary")
        self.reset_button.style().unpolish(self.reset_button)
        self.reset_button.style().polish(self.reset_button)
        button_box.addButton(self.reset_button, QDialogButtonBox.ActionRole)

        self.reset_button.clicked.connect(self._reset_to_default)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _with_browse(self, edit: QLineEdit, handler) -> QWidget:
        wrapper = QWidget(self)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("浏览", self)
        button.setProperty("variant", "secondary")
        button.style().unpolish(button)
        button.style().polish(button)
        button.clicked.connect(handler)
        layout.addWidget(edit)
        layout.addWidget(button)
        return wrapper

    def _choose_output_dir(self) -> None:
        self._choose_directory_for_edit(self.output_dir_edit)

    def _choose_ffmpeg_file(self) -> None:
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

    def _choose_directory_for_edit(self, edit: QLineEdit) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择目录", edit.text().strip() or "")
        if directory:
            edit.setText(directory)

    def _choose_file_for_edit(self, edit: QLineEdit, title: str, file_filter: str) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, title, edit.text().strip() or "", file_filter)
        if file_path:
            edit.setText(file_path)

    def _reset_to_default(self) -> None:
        self.user_request_edit.setPlainText(self.default_config.user_request)
        self.output_dir_edit.setText(self.default_config.output_dir)
        self.ffmpeg_path_edit.setText(self.default_config.ffmpeg_path)
        self.font_file_edit.setText(self.default_config.font_file)
        self.bgm_file_edit.setText(self.default_config.bgm_file)
        self.bgm_style_edit.setText(self.default_config.bgm_style)
        self.brief_path_edit.setText(self.default_config.brief_path)
        self.analysis_path_edit.setText(self.default_config.analysis_path)
        self.storyboard_path_edit.setText(self.default_config.storyboard_path)
        index = self.log_level_combo.findText((self.default_config.log_level or "INFO").upper())
        self.log_level_combo.setCurrentIndex(index if index >= 0 else 1)
        self.ignore_existing_checkbox.setChecked(self.default_config.ignore_existing_analysis)
        self.skip_ffmpeg_checkbox.setChecked(self.default_config.skip_ffmpeg)
        self.skip_model_checkbox.setChecked(self.default_config.skip_model)

    def build_config(self) -> TaskConfig:
        return replace(
            self.current_config,
            user_request=self.user_request_edit.toPlainText().strip(),
            output_dir=self.output_dir_edit.text().strip(),
            ffmpeg_path=self.ffmpeg_path_edit.text().strip(),
            font_file=self.font_file_edit.text().strip(),
            bgm_file=self.bgm_file_edit.text().strip(),
            bgm_style=self.bgm_style_edit.text().strip(),
            brief_path=self.brief_path_edit.text().strip(),
            analysis_path=self.analysis_path_edit.text().strip(),
            storyboard_path=self.storyboard_path_edit.text().strip(),
            log_level=self.log_level_combo.currentText(),
            ignore_existing_analysis=self.ignore_existing_checkbox.isChecked(),
            skip_ffmpeg=self.skip_ffmpeg_checkbox.isChecked(),
            skip_model=self.skip_model_checkbox.isChecked(),
        )


class MainWindow(QMainWindow):
    def __init__(self, settings_path: str | None = None) -> None:
        super().__init__()
        self.default_config_path = Path(settings_path).resolve() if settings_path else None
        self.default_config_source = describe_default_config_source(self.default_config_path)
        self.default_config = load_task_config(self.default_config_path)
        self.session_config = replace(self.default_config)
        self.state = AppState(config=replace(self.session_config))
        self.service = GuiTaskService(self.state)
        self.worker: TaskWorker | None = None
        self.result_dialog: ResultVideoDialog | None = None

        self.setWindowTitle("OV Video Editing Skills GUI")
        self.resize(1360, 860)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(INTEL_STYLE_SHEET)
        self._build_ui()
        self._load_config_into_form(self.session_config)
        self._append_log(f"[gui] 已加载 default config：{self.default_config_source}")

    def _build_ui(self) -> None:
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        central = QWidget(self)
        central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        root_layout.addWidget(self._build_header())

        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)

        left_layout.addWidget(self._build_main_config_group())
        left_layout.addWidget(self._build_settings_summary_group())
        left_layout.addWidget(self._build_preflight_group())
        left_layout.addWidget(self._build_action_group())
        left_layout.addStretch(1)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        right_layout.addWidget(self._build_status_group())
        right_layout.addWidget(self._build_video_group(), stretch=5)
        right_layout.addWidget(self._build_artifact_group(), stretch=4)
        right_layout.addWidget(self._build_log_group(), stretch=4)

        body_layout.addWidget(left_panel, 4)
        body_layout.addWidget(right_panel, 7)
        root_layout.addLayout(body_layout)
        scroll_area.setWidget(central)
        self.setCentralWidget(scroll_area)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("就绪")
        self._build_menu()

    def _build_header(self) -> QFrame:
        frame = QFrame(self)
        frame.setProperty("card", "hero")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("OV Video Editing Skills", self)
        title.setProperty("role", "title")
        subtitle = QLabel(
            "Intel 风格的本地视频分析 / 分镜 / 合成控制台。主界面仅保留核心三项参数，其余参数通过 Settings 临时覆盖。",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "subtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(settings_action)

        reload_default_action = QAction("重新加载 default config", self)
        reload_default_action.triggered.connect(self._reload_default_config)
        file_menu.addAction(reload_default_action)

        open_workspace_action = QAction("打开工作区", self)
        open_workspace_action.triggered.connect(self._open_workspace)
        file_menu.addAction(open_workspace_action)

        open_output_action = QAction("打开输出目录", self)
        open_output_action.triggered.connect(self._open_output_dir)
        file_menu.addAction(open_output_action)

    def _build_main_config_group(self) -> QGroupBox:
        group = QGroupBox("主界面参数", self)
        layout = QFormLayout(group)

        self.video_input_edit = QLineEdit(self)
        self.video_input_edit.textChanged.connect(self._update_selected_video_preview)
        self.model_dir_edit = QLineEdit(self)
        self.device_combo = QComboBox(self)
        self.device_combo.addItems(["GPU", "CPU"])

        layout.addRow("输入数据", self._with_browse(self.video_input_edit, self._choose_video_input))
        layout.addRow("模型路径", self._with_browse(self.model_dir_edit, self._choose_model_dir))
        layout.addRow("设备", self.device_combo)
        return group

    def _build_settings_summary_group(self) -> QGroupBox:
        group = QGroupBox("Settings 摘要", self)
        layout = QVBoxLayout(group)
        self.default_source_label = QLabel(f"default config：{self.default_config_source}", self)
        self.default_source_label.setWordWrap(True)
        self.default_source_label.setProperty("role", "subtitle")
        self.settings_summary_label = QLabel(self)
        self.settings_summary_label.setWordWrap(True)
        self.settings_summary_label.setProperty("role", "muted")

        settings_button = QPushButton("打开 Settings", self)
        settings_button.setProperty("variant", "secondary")
        settings_button.style().unpolish(settings_button)
        settings_button.style().polish(settings_button)
        settings_button.clicked.connect(self._open_settings_dialog)

        layout.addWidget(self.default_source_label)
        layout.addWidget(self.settings_summary_label)
        layout.addWidget(settings_button, alignment=Qt.AlignLeft)
        return group

    def _build_action_group(self) -> QGroupBox:
        group = QGroupBox("执行操作", self)
        layout = QGridLayout(group)

        self.prepare_button = QPushButton("Prepare", self)
        self.analyze_button = QPushButton("Analyze", self)
        self.storyboard_button = QPushButton("Storyboard", self)
        self.compose_button = QPushButton("Compose", self)
        self.e2e_button = QPushButton("E2E", self)
        self.settings_button = QPushButton("Settings", self)
        self.settings_button.setProperty("variant", "secondary")
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

        self.prepare_button.clicked.connect(lambda: self._start_task(TaskName.PREPARE))
        self.analyze_button.clicked.connect(lambda: self._start_task(TaskName.ANALYZE))
        self.storyboard_button.clicked.connect(lambda: self._start_task(TaskName.STORYBOARD))
        self.compose_button.clicked.connect(lambda: self._start_task(TaskName.COMPOSE))
        self.e2e_button.clicked.connect(lambda: self._start_task(TaskName.E2E))
        self.settings_button.clicked.connect(self._open_settings_dialog)

        layout.addWidget(self.e2e_button, 0, 0, 1, 2)
        layout.addWidget(self.prepare_button, 1, 0)
        layout.addWidget(self.analyze_button, 1, 1)
        layout.addWidget(self.storyboard_button, 2, 0)
        layout.addWidget(self.compose_button, 2, 1)
        layout.addWidget(self.settings_button, 3, 0, 1, 2)
        return group

    def _build_preflight_group(self) -> QGroupBox:
        group = QGroupBox("运行前检查", self)
        layout = QVBoxLayout(group)

        summary = QLabel("集中展示 Python、模型、ffmpeg、BGM 与输入数据状态，并同步提示高风险缺失项。", self)
        summary.setProperty("role", "subtitle")
        summary.setWordWrap(True)

        controls = QHBoxLayout()
        self.refresh_preflight_button = QPushButton("刷新检查", self)
        self.refresh_preflight_button.setProperty("variant", "secondary")
        self.refresh_preflight_button.style().unpolish(self.refresh_preflight_button)
        self.refresh_preflight_button.style().polish(self.refresh_preflight_button)
        self.refresh_preflight_button.clicked.connect(self._refresh_preflight_panel)
        controls.addWidget(self.refresh_preflight_button)
        controls.addStretch(1)

        self.issue_banner = QLabel("当前没有高优先级问题。", self)
        self.issue_banner.setWordWrap(True)
        self.issue_banner.setProperty("severity", "info")

        self.preflight_view = QPlainTextEdit(self)
        self.preflight_view.setReadOnly(True)
        self.preflight_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.preflight_view.setMinimumHeight(220)

        layout.addWidget(summary)
        layout.addLayout(controls)
        layout.addWidget(self.issue_banner)
        layout.addWidget(self.preflight_view)
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

    def _build_video_group(self) -> QGroupBox:
        group = QGroupBox("视频预览", self)
        layout = QVBoxLayout(group)
        self.video_player_widget = VideoPlayerWidget("已选择的视频", self)
        layout.addWidget(self.video_player_widget)
        return group

    def _build_artifact_group(self) -> QGroupBox:
        group = QGroupBox("工作区产物浏览", self)
        layout = QVBoxLayout(group)

        summary = QLabel("浏览工作区中间产物，并对 storyboard 提供结构化摘要预览。", self)
        summary.setProperty("role", "subtitle")
        summary.setWordWrap(True)

        controls = QHBoxLayout()
        self.refresh_artifacts_button = QPushButton("刷新产物", self)
        self.open_artifact_button = QPushButton("打开选中文件", self)
        self.open_artifact_button.setProperty("variant", "secondary")
        self.open_artifact_button.style().unpolish(self.open_artifact_button)
        self.open_artifact_button.style().polish(self.open_artifact_button)
        self.refresh_artifacts_button.clicked.connect(self._refresh_artifact_browser)
        self.open_artifact_button.clicked.connect(self._open_selected_artifact)
        controls.addWidget(self.refresh_artifacts_button)
        controls.addWidget(self.open_artifact_button)
        controls.addStretch(1)

        content = QHBoxLayout()
        self.artifact_list = QListWidget(self)
        self.artifact_list.setMinimumWidth(220)
        self.artifact_list.currentItemChanged.connect(self._handle_artifact_selection_changed)
        self.artifact_preview = QPlainTextEdit(self)
        self.artifact_preview.setReadOnly(True)
        self.artifact_preview.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        content.addWidget(self.artifact_list, 3)
        content.addWidget(self.artifact_preview, 5)

        layout.addWidget(summary)
        layout.addLayout(controls)
        layout.addLayout(content)
        return group

    def _with_browse(self, edit: QLineEdit, handler) -> QWidget:
        wrapper = QWidget(self)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        browse_button = QPushButton("浏览", self)
        browse_button.setProperty("variant", "secondary")
        browse_button.style().unpolish(browse_button)
        browse_button.style().polish(browse_button)
        browse_button.clicked.connect(handler)
        layout.addWidget(edit)
        layout.addWidget(browse_button)
        return wrapper

    def _collect_config(self) -> TaskConfig:
        return replace(
            self.session_config,
            video_input=self.video_input_edit.text().strip(),
            model_dir=self.model_dir_edit.text().strip(),
            device=self.device_combo.currentText(),
        )

    def _load_config_into_form(self, config: TaskConfig) -> None:
        self.video_input_edit.setText(config.video_input)
        self.model_dir_edit.setText(config.model_dir)
        index = self.device_combo.findText(config.device or "GPU")
        self.device_combo.setCurrentIndex(index if index >= 0 else 0)
        self._refresh_settings_summary()
        self._update_selected_video_preview()
        self._refresh_artifact_browser()
        self._refresh_preflight_panel()

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

    def _refresh_settings_summary(self) -> None:
        request = (self.session_config.user_request or "").strip()
        if len(request) > 36:
            request = request[:36] + "..."
        summary = [
            f"用户请求：{request or '未设置'}",
            f"输出目录：{self.session_config.output_dir or '使用工作区默认目录'}",
            f"ffmpeg：{self.session_config.ffmpeg_path or '按 default config / 自动发现'}",
            f"BGM：{self.session_config.bgm_file or '随机或 storyboard 指定'}",
            f"日志级别：{self.session_config.log_level or 'INFO'}",
            f"临时开关：ignore={self.session_config.ignore_existing_analysis}, skip_ffmpeg={self.session_config.skip_ffmpeg}, skip_model={self.session_config.skip_model}",
        ]
        self.settings_summary_label.setText("\n".join(summary))

    def _refresh_preflight_panel(self) -> None:
        config = self._collect_config()
        checks = collect_environment_checks(config)
        self.preflight_view.setPlainText(format_environment_checks(checks))
        issues = collect_diagnostic_issues(self.state, config)
        self._render_issue_banner(issues)

    def _render_issue_banner(self, issues: list[DiagnosticIssue]) -> None:
        if not issues:
            self.issue_banner.setProperty("severity", "info")
            self.issue_banner.setText("当前没有高优先级问题。")
        else:
            top_issue = next((issue for issue in issues if issue.severity == "error"), issues[0])
            self.issue_banner.setProperty("severity", top_issue.severity if top_issue.severity in {"error", "warning"} else "info")
            parts = [top_issue.summary, top_issue.detail]
            if top_issue.suggestion:
                parts.append(f"建议：{top_issue.suggestion}")
            self.issue_banner.setText("\n".join(parts))
        self.issue_banner.style().unpolish(self.issue_banner)
        self.issue_banner.style().polish(self.issue_banner)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in [self.prepare_button, self.analyze_button, self.storyboard_button, self.compose_button, self.e2e_button, self.settings_button]:
            button.setEnabled(enabled)
        self.refresh_artifacts_button.setEnabled(enabled)
        self.open_artifact_button.setEnabled(enabled)
        self.refresh_preflight_button.setEnabled(enabled)

    def _start_task(self, task_name: TaskName) -> None:
        config = self._collect_config()
        self.state.config = config
        self._set_buttons_enabled(False)
        self.state.status = TaskStatus.RUNNING
        self._refresh_status()
        self._append_log(f"[gui] default config 来源：{self.default_config_source}")

        self.worker = TaskWorker(self.service, task_name, config)
        self.worker.log_message.connect(self._append_log)
        self.worker.task_finished.connect(self._handle_task_finished)
        self.worker.task_failed.connect(self._handle_task_failed)
        self.worker.start()

    def _handle_task_finished(self, result) -> None:
        self._set_buttons_enabled(True)
        self.state.last_result = result
        self._refresh_status()
        self._refresh_form_from_state()
        self._refresh_preflight_panel()
        if result.succeeded:
            self._append_log(f"[gui] 任务成功：{result.task_name.value}")
            final_video = Path(result.artifacts.get("final_video", "")) if result.artifacts.get("final_video") else None
            if final_video and final_video.exists() and result.task_name in {TaskName.COMPOSE, TaskName.E2E}:
                self.result_dialog = ResultVideoDialog(final_video, self)
                self.result_dialog.show()
        else:
            self._append_log(f"[gui] 任务失败：{result.task_name.value}")
            QMessageBox.warning(self, "任务失败", result.stderr or result.stdout or "任务执行失败")

    def _handle_task_failed(self, message: str) -> None:
        self._set_buttons_enabled(True)
        self.state.status = TaskStatus.FAILED
        self._refresh_status()
        self._append_log(f"[gui] 异常：{message}")
        self._refresh_preflight_panel()
        QMessageBox.critical(self, "执行异常", message)

    def _refresh_form_from_state(self) -> None:
        self._refresh_settings_summary()
        if self.state.workspace_dir:
            self.workspace_label.setText(f"工作区：{self.state.workspace_dir}")
        self._refresh_artifact_browser()
        self._refresh_preflight_panel()

    def _reload_default_config(self) -> None:
        self.default_config = load_task_config(self.default_config_path)
        self.session_config = replace(self.default_config)
        self.state.config = replace(self.default_config)
        self._load_config_into_form(self.default_config)
        self._append_log(f"[gui] 已重新加载 default config：{self.default_config_source}")

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._collect_config(), self.default_config_source, self.default_config, self)
        if dialog.exec() == QDialog.Accepted:
            self.session_config = dialog.build_config()
            self._refresh_settings_summary()
            self._refresh_preflight_panel()
            self._append_log("[gui] 已应用 Settings 临时参数（仅当前会话生效）")

    def _refresh_artifact_browser(self) -> None:
        artifacts = collect_workspace_artifacts(self.state, self._collect_config())
        self.artifact_list.clear()
        self.artifact_preview.clear()

        if not artifacts:
            self.artifact_preview.setPlainText("当前没有可浏览的工作区产物。请先执行 Prepare / Analyze / Storyboard / E2E。")
            return

        for artifact in artifacts:
            status = "已生成" if artifact.exists else "未生成"
            item = QListWidgetItem(f"{artifact.label} · {status}")
            item.setData(Qt.UserRole, artifact)
            self.artifact_list.addItem(item)

        self.artifact_list.setCurrentRow(0)

    def _handle_artifact_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None = None) -> None:
        del previous
        if current is None:
            self.artifact_preview.clear()
            return
        artifact = current.data(Qt.UserRole)
        if not isinstance(artifact, WorkspaceArtifact):
            self.artifact_preview.clear()
            return
        self.artifact_preview.setPlainText(build_artifact_preview(artifact))

    def _open_selected_artifact(self) -> None:
        current = self.artifact_list.currentItem()
        if current is None:
            QMessageBox.information(self, "提示", "请先选择一个工作区产物。")
            return
        artifact = current.data(Qt.UserRole)
        if not isinstance(artifact, WorkspaceArtifact) or not artifact.exists:
            QMessageBox.information(self, "提示", "当前产物尚未生成，无法打开。")
            return
        path = Path(artifact.path)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "提示", f"无法打开文件：{path}")

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

    def _open_output_dir(self) -> None:
        output_dir = self.session_config.output_dir or self.state.workspace_dir
        if not output_dir:
            QMessageBox.information(self, "提示", "当前还没有可打开的输出目录。")
            return
        path = Path(output_dir)
        if not path.exists():
            QMessageBox.warning(self, "提示", f"输出目录不存在：{path}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "提示", f"无法打开输出目录：{path}")

    def _choose_video_input(self) -> None:
        current = self.video_input_edit.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(self, "选择视频文件", current or "", "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv);;所有文件 (*)")
        if file_path:
            self.video_input_edit.setText(file_path)
            return
        directory = QFileDialog.getExistingDirectory(self, "选择视频目录", current or "")
        if directory:
            self.video_input_edit.setText(directory)

    def _choose_model_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择模型目录", self.model_dir_edit.text().strip() or "")
        if directory:
            self.model_dir_edit.setText(directory)
            self._refresh_preflight_panel()

    def _resolve_preview_video_path(self) -> Path | None:
        raw_value = self.video_input_edit.text().strip()
        if not raw_value:
            return None
        candidate = Path(raw_value)
        if candidate.is_file() and candidate.suffix.lower() in VIDEO_EXTENSIONS:
            return candidate
        if candidate.is_dir():
            videos = sorted(
                path for path in candidate.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
            )
            if videos:
                return videos[0]
        return None

    def _update_selected_video_preview(self) -> None:
        self.video_player_widget.set_video(self._resolve_preview_video_path())
        self._refresh_preflight_panel()


def run_gui(settings_path: str | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("OV Video Editing Skills GUI")
    app.setStyleSheet(INTEL_STYLE_SHEET)
    window = MainWindow(settings_path=settings_path)
    window.show()
    return int(app.exec())