# ov-video-editing-skills 开发状态归档

更新时间：2026-05-11

## 1. 项目定位

`ov-video-editing-skills` 是一个不依赖 VS Code skill 运行时的本地纯 Python vlog 剪辑工具。

当前目标是把 `video-editing-skills` 中的参考工作流逐步本地化，形成以下可独立运行链路：

1. 检查当前 `conda` 环境与本地资源
2. 扫描视频目录或单视频文件并创建工作区
3. 自动生成 `creative_brief.json`
4. 使用 OpenVINO VLM 输出 `output_vlm.json`
5. 生成本地 `storyboard.json`
6. 使用 FFmpeg 合成成片

---

## 2. 开发规范

当前阶段默认遵循以下规范：

1. 每个新增功能都补对应单元测试。
2. 不创建新的 Python `venv`。
3. 默认只面向用户现有的 `conda` 环境提供运行说明。
4. 所有需要下载的模型或外部文件，只提供下载路径与下载方法，由用户手动下载。
5. 代码运行和验证由用户执行，开发侧不擅自代跑。

补充执行约束：

- 默认面向 Windows `cmd` / `conda` 使用场景整理命令。
- 本地大文件与资源目录不纳入 Git 版本管理。
- 优先修复流程断点和阶段衔接问题，再做体验优化。
- 文档说明必须与代码当前行为保持一致。

---

## 3. 当前开发计划

### 已完成

- 梳理 `ov-video-editing-skills` 与 `video-editing-skills` 的结构差异。
- 补齐 `creative_brief` 贯穿 `prepare -> analyze -> storyboard` 的链路。
- 修复 CLI 子命令二次解析问题。
- 让 `prepare` 支持单视频文件输入。
- 增加“快速模式”，可复用已有 `output_vlm.json`。
- 将运行时改为复用当前 `conda` Python，不再创建 `.venv`。
- 将 `setup-resources` / `setup-model` 改成仅检查、不自动下载。
- 处理 Windows 控制台中文输出编码兼容问题。
- 建立独立 Git 仓库并补齐提交辅助脚本。
- 为 E2E pipeline 补齐 `wheel` 打包入口，并提供 Windows `exe` 构建配置。
- 补充 `build_e2e_exe.cmd`，用于 Windows 下一键构建 E2E 可执行文件。

### 进行中 / 下一步建议

1. 让 `analyze` 与 `prepare` 一致，支持单视频文件直接输入。
2. 优化会议类素材的片段去重和高光选择逻辑。
3. 增强 `storyboard` 对 `seg_id` / 来源片段的引用约束。
4. 为 `compose` 增加更清晰的阶段输出说明与异常提示。
5. 继续完善测试覆盖，特别是 `analyze` 和 `compose` 的边界场景。
6. 在目标机器继续验证 `wheel` / `exe` 对外部资源路径的兼容性。

---

## 4. 当前开发进展

### 4.1 工作区准备链路

已完成：

- `prepare` 支持输入视频目录或单个视频文件。
- 自动创建 `editing_YYYYMMDD_HHMMSS` 工作区。
- 自动生成：
  - `user_input.txt`
  - `creative_brief.json`
  - `runtime_env.json`
- 若工作目录下已有有效 `output_vlm.json`，会自动复制到工作区作为快速模式输入。
- `runtime_env.json` 已记录当前解释器路径、`conda` 环境名和资源检查结果。

### 4.2 Creative Brief 机制

已完成：

- 从用户请求中抽取：
  - 目标时长
  - 主题
  - 氛围
  - 节奏
  - 必须保留要素
- 自动生成分析提示词。
- `analyze` 与 `storyboard` 可自动继承该信息。

### 4.3 CLI 与命令流

已完成：

- 修复 `python run.py prepare ...` 这类子命令会被二次解析的问题。
- 目前 `prepare`、`analyze`、`storyboard`、`compose`、`e2e` 均由 `run.py` 统一分发。

### 4.4 打包与移植

已完成：

- 新增 `pyproject.toml`，支持构建 `wheel`。
- 新增可安装命令入口：
  - `ov-video-editing-skills`
  - `ov-video-editing-e2e`
- 新增 `ov_video_editing_e2e.spec`，支持使用 `PyInstaller` 构建 Windows `exe`。
- 新增 `build_e2e_exe.cmd`，封装 `PyInstaller` 调用，减少手工输入。
- 将 `scripts/test_e2e.py` 的核心逻辑收敛到包内模块，便于安装后直接调用。

### 4.5 资源与环境策略

已完成：

- 代码运行默认复用当前激活的 `conda` 环境。
- 不再自动创建 `.venv`。
- `bootstrap` 仅做检查：
  - Python 版本
  - `ffmpeg` / `ffprobe`
  - OpenVINO 模型目录
- `setup_resources.py` 仅报告缺失路径和手动下载地址。
- `setup_ov_model.py` 仅报告模型缺失情况和手动放置目录。

### 4.6 分镜与合成

已完成：

- `storyboard` 已支持自动继承 `creative_brief.json`。
- 已生成更接近叙事结构的字段：
  - `story_outline.emotional_arc`
  - `story_outline.must_capture`
  - `clips[].narrative_role`
- `compose` 可继续使用生成的 `storyboard.json` 合成视频。

### 4.7 已补单元测试

当前已在 `tests/test_creative_flow.py` 覆盖：

- `creative_brief` 参数抽取
- `storyboard` 自动继承 brief
- `prepare` 复用已有 `output_vlm.json`
- `prepare` 忽略已有 `output_vlm.json`
- `prepare` 支持单文件输入
- CLI 子命令参数转发
- `e2e` 子命令入口暴露
- `pyproject.toml` 中可安装 console script 声明
- `runtime_summary()` 使用当前 Python / conda 信息
- `bootstrap_environment()` 只做检查，不做自动下载 / 安装

---

## 5. 当前关键文件变更

本阶段重点修改文件包括：

- `run.py`
- `README.md`
- `pyproject.toml`
- `requirements-build.txt`
- `ov_video_editing_e2e.spec`
- `build_e2e_exe.cmd`
- `ov_video_editing_skills/cli.py`
- `ov_video_editing_skills/e2e.py`
- `ov_video_editing_skills/prepare_workspace.py`
- `ov_video_editing_skills/creative_brief.py`
- `ov_video_editing_skills/analyze_video.py`
- `ov_video_editing_skills/generate_storyboard.py`
- `ov_video_editing_skills/runtime.py`
- `ov_video_editing_skills/bootstrap.py`
- `ov_video_editing_skills/setup_resources.py`
- `ov_video_editing_skills/setup_ov_model.py`
- `tests/test_creative_flow.py`
- `tests/test_command_scripts.py`

---

## 6. 当前已知问题与风险

1. `analyze` 当前更偏向目录扫描模式；单视频文件输入兼容性建议继续增强。
2. 会议 / 演讲类视频片段描述较为同质，后续需要更强的去重和高光筛选。
3. `compose` 的完整效果仍需由用户在目标环境中执行验证。
4. Git 仓库已独立初始化，但首次提交前需确保本地 `git user.name` / `git user.email` 已配置。

---

## 7. Git 保存建议

当前目录已经初始化为独立 Git 仓库。

推荐使用根目录下的提交脚本：

- `git_save_progress.cmd`

示例：

```bat
cd /d c:\Users\kundaxu\Downloads\xkd\ov-video-editing-skills
git_save_progress.cmd "checkpoint: 保存当前开发进展"
```

如果不传提交信息，脚本会使用默认提交信息：

```text
checkpoint: save current development progress
```

---

## 8. 建议的下一开发迭代

建议下一轮优先做以下两项：

1. `analyze` 支持单视频文件路径输入。
2. `storyboard` 增强高光片段筛选和重复描述去重。

这样可以让当前工作流更稳定、更贴近真实 vlog 场景。
