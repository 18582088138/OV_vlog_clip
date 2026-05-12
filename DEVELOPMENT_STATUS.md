# ov-video-editing-skills 开发状态归档

更新时间：2026-05-12

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

### GUI 开发计划（新增）

目标：

- 为当前 `prepare -> analyze -> storyboard -> compose -> e2e` 流程提供桌面 GUI。
- 优先保证“便于打包”和“便于在 Windows / Linux / macOS 部署”。
- 保持现有 CLI 为核心执行层，GUI 只做参数组织、进度展示、结果浏览和配置管理。

技术路线：

- GUI 层优先选用 `PySide6 / Qt for Python`。
- 原因：
  - 跨平台成熟，Windows / Linux / macOS 支持较稳定。
  - 与 Python 打包工具适配成熟，便于后续做 `PyInstaller` / `Nuitka` 打包。
  - 原生桌面交互能力完整，适合文件选择、任务进度、日志面板、表单配置和结果预览。
- 保持“不把业务逻辑写进界面层”的原则：
  - `ov_video_editing_skills/*` 继续作为核心业务模块。
  - 新增 GUI 目录只调用现有 Python API 或 CLI 入口。

分阶段计划：

#### Phase 1：GUI 架构收敛

1. 新增 `gui/` 或 `ov_video_editing_skills/gui/` 模块，建立独立入口。
2. 设计统一 `AppState` / `TaskConfig` / `TaskResult` 数据结构。
3. 把现有 CLI 可复用逻辑进一步收敛为可直接调用的 Python 函数，减少 GUI 通过子进程拼命令。
4. 先确定日志输出、错误捕获、任务取消、临时目录和结果路径的统一机制。

交付目标：

- GUI 启动后可加载基础窗口。
- 可以读取 / 保存基础配置。
- 可以复用现有 E2E 核心模块而不复制逻辑。

#### Phase 2：最小可用 GUI（MVP）

1. 首页仅保留以下基础输入：
  - 输入数据（视频目录 / 单视频文件）
  - 模型路径
  - 设备
2. 其余路径和运行参数通过 `Settings` 对话框临时覆盖：
  - 用户请求
  - 输出目录
  - `ffmpeg` 路径
  - 字体 / BGM / brief / analysis / storyboard 路径
  - `ignore-existing-analysis` / `skip-ffmpeg` / `skip-model`
3. 所有 GUI 参数首先从 `default config` 加载默认值；如用户打开 `Settings` 修改，则仅对当前 GUI 会话生效。
4. 主界面增加当前所选视频的内嵌预览区；当输入为目录时，默认预览目录中的第一个视频文件。
5. 在 `compose` / `e2e` 成功后，自动弹出新的播放窗口预览生成成片。
6. 界面风格采用偏 Intel 风格的蓝白灰配色和卡片式布局，不使用任何 logo，但保持技术感和简洁感。
7. 提供以下操作按钮：
  - `Prepare`
  - `Analyze`
  - `Storyboard`
  - `Compose`
  - `E2E`
8. 增加实时日志面板，展示当前阶段输出。
9. 增加任务状态展示：等待 / 运行中 / 成功 / 失败。
10. 增加“打开工作区”“打开输出目录”能力，便于调试和排障。

交付目标：

- GUI 可以完整驱动一次本地工作流。
- GUI 与 CLI 输出结果保持一致。
- 用户无需手工记忆命令即可完成标准流程。
- 主界面参数密度降低，默认配置与临时设置的职责边界清晰。
- 用户能直接在 GUI 中预览输入视频和输出成片。

#### Phase 3：结果浏览与可视化增强

1. 增加工作区浏览器：
  - `user_input.txt`
  - `*_brief.json`
  - `*_output_vlm.json`
  - `*_storyboard.json`
  - `runtime_env.json`
2. 增加 storyboard 结构化预览：
  - 分镜列表
  - 字幕文案
  - 转场
  - BGM 选择结果
3. 增加错误高亮与缺失依赖提示。
4. 增加运行前检查页面，集中展示 Python / 模型 / `ffmpeg` / BGM 状态。

交付目标：

- GUI 不仅能执行任务，还能辅助用户理解中间产物和问题定位。

#### Phase 4：跨平台打包与部署完善

1. Windows：优先支持 `PyInstaller` 单目录 / 单文件打包。
2. Linux：优先验证 `PyInstaller` 单目录包与 `wheel` 安装运行。
3. macOS：优先验证源码运行与 `app bundle` 可行性，后续再决定是否加入签名 / notarization 流程。
4. 将 GUI 与 CLI 共享一套资源定位逻辑，避免打包后路径分叉。
5. 补充平台相关文档：
  - 启动方式
  - 外部资源放置方式
  - 模型目录指定方式
  - `ffmpeg` 路径设置方式

交付目标：

- 至少完成 Windows 主平台 GUI 打包闭环。
- Linux / macOS 保持源码可运行，并预留后续打包扩展位。

界面规划原则：

- 采用单窗口多面板结构，避免多窗口过度分散。
- 优先使用“左侧流程导航 + 右侧配置 / 日志 / 结果”的布局。
- 主界面只展示高频核心参数；扩展参数进入 `Settings`。
- 所有关键路径都提供文件选择器，不要求用户手输路径。
- 日志区保留原始命令和阶段标签，便于与 CLI 对照。
- 长任务默认异步执行，避免界面卡死。
- 视觉风格以 Intel 风格的蓝白灰为主，强调专业、清爽和工程感。

打包与部署约束：

- GUI 不直接耦合 `conda` 专属逻辑，环境探测要兼容普通 Python 安装方式。
- GUI 仍复用当前资源目录规范：`bin/`、`models/`、`resource/`。
- 不把模型、视频、`ffmpeg` 二进制直接打进默认 Git 仓库。
- 打包时优先保证“核心功能可运行”，再做美化和高级交互。

建议的 GUI 开发顺序：

1. 先补底层可复用 API。
2. 再做 GUI MVP。
3. 然后补结果浏览与依赖检查。
4. 最后处理跨平台打包细节。

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

### 4.8 GUI 当前进展

已完成：

- GUI 主界面已收敛为 `输入数据`、`模型路径`、`设备` 三项主参数。
- 其余路径和运行开关已集中到 `Settings` 对话框，并以 `default config` 为默认来源。
- 主界面已支持输入视频预览，`compose` / `e2e` 成功后可弹窗播放成片。
- 已进入 Phase 3 的首批实现：
  - 浏览 `user_input.txt`
  - 浏览 `*_brief.json`
  - 浏览 `*_output_vlm.json`
  - 浏览 `*_storyboard.json`
  - 浏览 `runtime_env.json`
  - 对 storyboard 提供结构化摘要预览，便于检查分镜数量、字幕、转场与 BGM 结果
- 已补第二批 Phase 3 能力：
  - 运行前检查面板，可集中查看 Python、输入数据、模型目录、`ffmpeg` / `ffprobe` 与 BGM 状态
  - 任务失败后基于日志关键字提示缺失依赖和高风险问题，便于快速排障
- 已开始推进 Phase 4 第一批能力：
  - 新增 `ov_video_editing_gui.spec`，用于 Windows GUI `PyInstaller` 打包
  - 新增 `build_gui_exe.cmd`，用于 Windows 下一键构建 GUI 单目录包
  - GUI 打包默认携带 `default_config.json`，并复用当前 `bin/`、`models/`、`resource/` 资源定位约定

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

如果开始进入 GUI 开发，建议把下一轮迭代调整为：

1. 收敛 GUI 所需的底层可复用 API，减少对子进程命令拼接的依赖。
2. 基于 `PySide6` 落一个可运行的 GUI MVP：文件选择、参数输入、日志面板、E2E 执行。
3. 再补平台打包脚本与 GUI 专属使用文档。

这样可以让当前工作流更稳定、更贴近真实 vlog 场景。
