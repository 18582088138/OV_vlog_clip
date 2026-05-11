# ov-video-editing-skills

一个不依赖 VS Code skill 运行时的本地纯 Python vlog 剪辑工具。

它复用了 `video-editing-skills` 中的视频分析与合成思路，并补了一个本地可直接运行的分镜生成器，形成完整流程：

1. 检查当前 `conda ov_env_py312` 与本地资源
2. 扫描视频目录并生成工作区
3. 自动解析用户剪辑诉求，生成 `creative_brief.json`
3. 用 OpenVINO VLM 分析视频，输出 `output_vlm.json`
4. 基于分析结果生成 `storyboard.json`
5. 用 FFmpeg 合成带字幕 / 转场 / BGM 的成片

## 目录

- `run.py`：统一入口
- `ov_video_editing_skills/`：核心 Python 包
- `resource/bgm/`：本地 BGM 目录
- `requirements.txt`：Python 依赖

## 快速开始

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
- `creative_brief.json`：自动抽取的时长 / 主题 / 氛围 / 节奏 / 必保留要素
- `runtime_env.json`：本地运行时清单
- 如果输入目录或单视频所在目录下的 `output_vlm.json` 已存在且格式有效，会自动复制到工作区，作为“快速模式”复用结果

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
python run.py analyze --video-dir "D:\videos" --output "D:\videos\editing_20260511_120000\output_vlm.json"
```

如果 `output_vlm.json` 所在目录存在 `creative_brief.json`，`analyze` 会自动继承其中的分析提示词；也可以手动传：

```bat
python run.py analyze --video-dir "D:\videos" --output "D:\videos\editing_20260511_120000\output_vlm.json" --brief "D:\videos\editing_20260511_120000\creative_brief.json"
```

### 5. 生成分镜

```bat
python run.py storyboard --analysis "D:\videos\editing_20260511_120000\output_vlm.json" --output "D:\videos\editing_20260511_120000\storyboard.json" --target-duration 30 --theme "城市漫步" --mood "轻松愉悦"
```

如果同目录下已有 `creative_brief.json`，未显式传入的 `target-duration` / `theme` / `mood` / `pacing` / `must-capture` 会自动继承，生成的分镜还会补充：

- `story_outline.emotional_arc`
- `story_outline.must_capture`
- `clips[].narrative_role`

### 6. 合成成片

```bat
python run.py compose --storyboard "D:\videos\editing_20260511_120000\storyboard.json"
```

## 主要命令

- `python run.py prepare --video-dir ...`
- `python run.py prepare --video-dir ... --ignore-existing-analysis`
- `python run.py analyze --video-dir ... --output ...`
- `python run.py storyboard --analysis ... --output ...`
- `python run.py compose --storyboard ...`

## 分镜生成说明

`storyboard` 子命令是本项目新增的本地实现，不依赖 skill agent。
它会：

- 从 `output_vlm.json` 中提取有效片段
- 自动读取 `creative_brief.json` 并继承用户诉求
- 按目标时长筛选镜头
- 按开场 / 展开 / 高光 / 收束生成更贴近叙事的字幕文案
- 自动分配转场
- 尝试从 `resource/bgm/` 中选择匹配的 BGM

## 与 `video-editing-skills` 的差异

- `video-editing-skills`：面向 skill 运行时，阶段 3 依赖 agent 生成 `storyboard.json`
- `ov-video-editing-skills`：完全本地运行，阶段 3 由 Python 直接生成分镜
- 当前版本额外补齐了“用户请求 → creative brief → 分析 prompt / 分镜参数自动继承”的链路
- 当前版本补齐了参考工作流中的“快速模式”：若 `VIDEO_DIR` 下已有 `output_vlm.json`，`prepare` 会自动复制到新工作区

## 注意事项

- `analyze` 依赖 OpenVINO 与模型目录
- `compose` 依赖 `ffmpeg` / `ffprobe`
- 如果 `resource/bgm/` 中没有 `.mp3`，仍可生成无 BGM 成片
- 当前默认面向 Windows
- 默认按现有 `conda ov_env_py312` 提供命令说明；模型和外部资源需由用户手动下载并放置
- `setup-resources` / `setup-model` 当前为检查脚本：只输出缺失路径与手动放置方法，不会自动下载
