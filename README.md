# ov-video-editing-skills

一个不依赖 VS Code skill 运行时的本地纯 Python vlog 剪辑工具。

它复用了 `video-editing-skills` 中的视频分析与合成思路，并补了一个本地可直接运行的分镜生成器，形成完整流程：

1. 检查当前 `conda ov_env_py312` 与本地资源
2. 扫描视频目录并生成工作区
3. 自动解析用户剪辑诉求，生成与视频名相关的 `*_brief.json`
4. 用 OpenVINO VLM 分析视频，输出与视频名相关的 `*_output_vlm.json`
5. 基于分析结果生成与素材名相关的 `*_storyboard.json`
6. 用 FFmpeg 合成带字幕 / 转场 / BGM 的成片

## 目录

- `run.py`：统一入口
- `ov_video_editing_skills/`：核心 Python 包
- `resource/bgm/`：本地 BGM 目录
- `requirements.txt`：Python 依赖
- `requirements-gui.txt`：GUI 依赖
- `pyproject.toml`：`wheel` 打包配置与可安装命令入口
- `ov_video_editing_e2e.spec`：Windows `exe` 打包配置（PyInstaller）
- `build_e2e_exe.cmd`：Windows 下一键构建 `ov-video-editing-e2e.exe`

## 可移植打包

当前仓库已把 E2E pipeline 收敛为包内入口，可按两种方式分发：

1. 跨平台优先：构建并分发 `wheel`
2. Windows 单文件分发：构建 `exe`

这两种封装都复用当前项目代码，不会额外创建新的 `.venv`，仍建议在你已有的 `conda` 环境中构建。

### 1. 构建 `wheel`

先激活你当前使用的 `conda` 环境，再安装构建依赖：

```bat
cd /d c:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills
conda activate ov_env_py312
python -m pip install -r requirements-build.txt
python -m build --wheel
```

成功后会在 `dist\` 下生成类似：

- `ov_video_editing_skills-0.3.0-py3-none-any.whl`

在其他平台安装后，可直接使用两个入口命令：

- `ov-video-editing-skills`
- `ov-video-editing-e2e`

例如：

```bat
pip install dist\ov_video_editing_skills-0.3.0-py3-none-any.whl
ov-video-editing-e2e --video-dir "D:\videos" --dry-run
```

### 2. 构建 Windows `exe`

项目根目录已提供 `PyInstaller` 规格文件：`ov_video_editing_e2e.spec`

也提供了一键脚本：`build_e2e_exe.cmd`

推荐直接使用：

```bat
cd /d c:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills
conda activate ov_env_py312
build_e2e_exe.cmd
```

如需透传额外参数给 `PyInstaller`，可直接追加：

```bat
build_e2e_exe.cmd --noconfirm
```

等价的底层命令仍然是：

```bat
cd /d c:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills
conda activate ov_env_py312
python -m pip install -r requirements-build.txt
pyinstaller ov_video_editing_e2e.spec --clean
```

成功后，单文件可执行程序位于：

- `dist\ov-video-editing-e2e.exe`

使用示例：

```bat
dist\ov-video-editing-e2e.exe --video-dir "D:\videos" --dry-run
```

说明：

- `wheel` 更适合 Linux / macOS / Windows 间移植
- `exe` 仅适合 Windows 分发
- 运行时仍需用户手动准备模型、`ffmpeg` / `ffprobe` 和相关资源
- `compose` 输出效果仍建议在目标机器上实际验证
- `build_e2e_exe.cmd` 会优先使用当前激活 `conda` 环境中的 `pyinstaller.exe`

## 快速开始

### GUI 启动（Phase 1 骨架）

当前仓库已经加入 GUI 基础骨架，优先用于：

- 通过 `default config` 自动加载默认参数
- 主界面只保留 `输入数据`、`模型路径`、`设备` 三项主参数
- 通过 `Settings` 对话框临时覆盖其他参数
- 调用 `prepare` / `analyze` / `storyboard` / `compose` / `e2e`
- 查看实时日志
- 预览当前所选视频
- 在 `compose` / `e2e` 成功后弹窗播放生成的成片

安装 GUI 依赖：

```bat
cd /d c:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills
conda activate ov_env_py312
python -m pip install -r requirements-gui.txt
```

启动方式：

```bat
python run.py gui
```

如果你想指定一份自定义 `default config`，也可以传：

```bat
python run.py gui --settings "C:\path\to\custom_gui_config.json"
```

或者安装为包后启动：

```bat
ov-video-editing-skills gui
ov-video-editing-gui
```

说明：

- 当前 GUI 处于 Phase 1 / Phase 2 过渡阶段，重点是默认配置、Settings 临时参数、视频预览与任务调度打通。
- 若未安装 `PySide6`，GUI 启动时会给出明确提示，不会影响 CLI 主流程。

### 1. 激活现有 `conda ov_env_py312`

```bat
cd /d c:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills
conda activate ov_env_py312
```

### 2. 手动准备模型与外部文件

- `ffmpeg.exe` / `ffprobe.exe`：手动下载后放到 `bin/`
- OpenVINO VLM 模型：手动下载 `OpenVINO/Qwen2.5-VL-7B-Instruct-int4-ov`，放到 `models/Qwen2.5-VL-7B-Instruct-int4/`
- 可选 BGM：手动放到 `resource/bgm/`

建议下载方式：

- 从浏览器直接下载发布包或模型文件
- 使用你自己的下载工具下载后手动解压 / 拷贝到以上目录
- 如果使用镜像站，请自行确认来源可信且目录结构完整

### 3. 创建工作区

```bat
python run.py prepare --video-dir "C:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills\videos\2022yunqidahui.mp4" --user-request "做一个30秒的视频总结vlog"
```

`--video-dir` 当前兼容两种输入：

- 视频目录：扫描目录顶层的所有视频文件
- 单个视频文件：只处理该文件，并在它所在目录创建工作区

执行后会在工作区额外生成：

- `user_input.txt`：原始用户请求
- `*_brief.json`：自动抽取的时长 / 主题 / 氛围 / 节奏 / 必保留要素；单视频输入时默认形如 `2022yunqidahui_brief.json`
- `runtime_env.json`：本地运行时清单
- 如果输入目录或单视频所在目录下存在与视频名相关的 `*_output_vlm.json`（或 legacy `output_vlm.json`）且格式有效，会自动复制到工作区，作为“快速模式”复用结果

`prepare` 当前只会：

- 检查当前 Python / `conda` 环境是否满足最低版本
- 检查 `bin/` 下的 `ffmpeg` / `ffprobe`
- 检查 `models/Qwen2.5-VL-7B-Instruct-int4/` 是否已手动放置
- 不创建新的 `.venv`
- 不自动下载任何模型或外部文件

如果你希望忽略已有分析结果、强制后续重新分析：

```bat
python run.py prepare --video-dir "D:\videos" --user-request "做一个30秒的轻松旅行vlog" --ignore-existing-analysis
```

### 4. 分析视频

```bat
python run.py analyze --video-dir "D:\videos"
```

`analyze` 现在同时支持：

- 传入视频目录：扫描目录顶层视频，并默认输出到 `<目录名>_output_vlm.json`
- 传入单个视频：只分析该文件，并默认输出到 `<视频名>_output_vlm.json`

如果工作区目录中存在同名 `*_brief.json`，`analyze` 会自动继承其中的分析提示词；也可以手动传：

```bat
python run.py analyze --video-dir "D:\videos\2022yunqidahui.mp4" --brief "D:\videos\editing_20260511_120000\2022yunqidahui_brief.json"
```

### 4.1 测试 `prepare` / `analyze` / `storyboard` / `compose` / `e2e` 的辅助脚本

仓库内新增了五个辅助测试脚本，方便你快速验证命令参数和调用链：

- `scripts\test_prepare.cmd`
- `scripts\test_analyze.cmd`
- `scripts\test_storyboard.cmd`
- `scripts\test_compose.cmd`
- `scripts\test_e2e.cmd`

对应的 Python 主脚本为：

- `scripts/test_prepare.py`
- `scripts/test_analyze.py`
- `scripts/test_storyboard.py`
- `scripts/test_compose.py`
- `scripts/test_e2e.py`

此外，安装 `wheel` 后也可以直接调用包内入口，不依赖仓库下的 `scripts\*.cmd`：

```bat
ov-video-editing-skills e2e --video-dir "D:\videos" --dry-run
ov-video-editing-e2e --video-dir "D:\videos" --dry-run
```

直接使用默认测试素材：

```bat
scripts\test_prepare.cmd --dry-run
scripts\test_analyze.cmd --dry-run
scripts\test_storyboard.cmd --dry-run
scripts\test_compose.cmd --dry-run
scripts\test_e2e.cmd --dry-run
```

指定单个视频文件：

```bat
scripts\test_prepare.cmd --video-dir "C:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills\videos\2022yunqidahui.mp4" --user-request "做一个30秒的视频总结vlog"
scripts\test_analyze.cmd --video-dir "C:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills\videos\2022yunqidahui.mp4"
scripts\test_storyboard.cmd --analysis "C:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills\videos"
scripts\test_compose.cmd --storyboard "C:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills\videos"
scripts\test_e2e.cmd --video-dir "C:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills\videos\2022yunqidahui.mp4" --user-request "做一个30秒的视频总结vlog"
```

如果需要透传更多参数给真实命令，也可以直接追加，例如：

```bat
scripts\test_prepare.cmd --video-dir "D:\videos" --ignore-existing-analysis -- --skip-model
scripts\test_analyze.cmd --video-dir "D:\videos" -- --device CPU --seg-duration 2.5
scripts\test_storyboard.cmd --analysis "D:\videos" -- --target-duration 30 --mood "轻松愉悦"
scripts\test_compose.cmd --storyboard "D:\videos" -- --dry-run
scripts\test_e2e.cmd --video-dir "D:\videos" --ignore-existing-analysis --output-dir "D:\videos\final_output"
```

说明：

- `--dry-run` 只打印最终执行命令，不实际运行
- 未传 `--video-dir` 时，会优先尝试仓库内的 `videos\2022yunqidahui.mp4`，其次尝试 `videos\`
- `test_analyze` 的 `--brief`、`--output` 都是可选；不传时仍走 `analyze` 当前的自动发现 / 自动命名逻辑
- `test_storyboard` 支持传分析结果文件，也支持直接传工作目录；`--output`、`--brief` 都可选
- `test_compose` 支持传 storyboard 文件，也支持直接传工作目录；`--output-dir` 可选
- `test_e2e` 会按 `prepare -> analyze -> storyboard -> compose` 顺序串联执行；`--dry-run` 时会打印完整命令链，真正执行时会自动解析 `prepare` 生成的工作区并串联后续阶段

### 5. 生成分镜

```bat
python run.py storyboard --analysis "D:\videos\editing_20260511_120000"
```

`storyboard` 现在同时支持：

- 传入分析结果文件：直接读取该 `*_output_vlm.json` / `output_vlm.json`
- 传入工作目录：自动发现目录下的分析结果文件，并默认输出 `<素材名>_storyboard.json`

默认输出命名规则：

- 分析文件为 `2022yunqidahui_output_vlm.json` 时，默认输出 `2022yunqidahui_storyboard.json`
- 如果使用 legacy `output_vlm.json`，则默认回退到按目录名生成 `*_storyboard.json`

如果同目录下已有 `*_brief.json`（兼容 legacy `creative_brief.json`），未显式传入的 `target-duration` / `theme` / `mood` / `pacing` / `must-capture` 会自动继承，生成的分镜还会补充：

- `story_outline.emotional_arc`
- `story_outline.must_capture`
- `clips[].narrative_role`

### 6. 合成成片

```bat
python run.py compose --storyboard "D:\videos\editing_20260511_120000"
```

`compose` 现在同时支持：

- 传入 storyboard 文件：直接合成该分镜
- 传入工作目录：自动发现目录下的 `*_storyboard.json` / `storyboard.json`

## 主要命令

- `python run.py prepare --video-dir ...`
- `python run.py prepare --video-dir ... --ignore-existing-analysis`
- `python run.py analyze --video-dir ...`
- `python run.py analyze --video-dir ... --output ...`
- `python run.py e2e --video-dir ...`
- `ov-video-editing-skills e2e --video-dir ...`
- `ov-video-editing-e2e --video-dir ...`
- `scripts\test_prepare.cmd ...`
- `scripts\test_analyze.cmd ...`
- `scripts\test_e2e.cmd ...`
- `python run.py storyboard --analysis ...`
- `python run.py storyboard --analysis ... --output ...`
- `scripts\test_storyboard.cmd ...`
- `python run.py compose --storyboard ...`
- `scripts\test_compose.cmd ...`

## 分镜生成说明

`storyboard` 子命令是本项目新增的本地实现，不依赖 skill agent。
它会：

- 从 `*_output_vlm.json`（兼容 `output_vlm.json`）中提取有效片段
- 自动读取 `*_brief.json`（兼容 `creative_brief.json`）并继承用户诉求
- 按目标时长筛选镜头
- 按开场 / 展开 / 高光 / 收束生成更贴近叙事的字幕文案
- 自动分配转场
- 尝试从 `resource/bgm/` 中选择匹配的 BGM

## 与 `video-editing-skills` 的差异

- `video-editing-skills`：面向 skill 运行时，阶段 3 依赖 agent 生成 `storyboard.json`
- `ov-video-editing-skills`：完全本地运行，阶段 3 由 Python 直接生成与素材名相关的 `*_storyboard.json`
- 当前版本额外补齐了“用户请求 → creative brief → 分析 prompt / 分镜参数自动继承”的链路
- 当前版本补齐了参考工作流中的“快速模式”：若 `VIDEO_DIR` 下已有 `*_output_vlm.json`（兼容 legacy `output_vlm.json`），`prepare` 会自动复制到新工作区

## 注意事项

- `analyze` 依赖 OpenVINO 与模型目录
- `compose` 依赖 `ffmpeg` / `ffprobe`
- 如果 `resource/bgm/` 中没有 `.mp3`，仍可生成无 BGM 成片
- 当前默认面向 Windows
- 默认按现有 `conda ov_env_py312` 提供命令说明；模型和外部资源需由用户手动下载并放置
- `setup-resources` / `setup-model` 当前为检查脚本：只输出缺失路径与手动放置方法，不会自动下载
- 工作区目录仍保留时间戳便于区分批次，但 `brief` / `analysis` 文件名只与视频名或目录名相关，方便后续读取
- `wheel` / `exe` 仅封装命令入口与 Python 逻辑，不内置模型、视频素材和 `ffmpeg`
