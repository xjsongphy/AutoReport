# AutoReport

[English](README.md)

---

基于多 Agent 协作的自动化物理实验报告撰写系统。用户提供实验数据和参考资料，Agent 团队通过理论推导、数据分析、可视化绘图和 LaTeX 排版，自动生成完整的实验报告。

## 功能特性

### 核心能力
- **多 Agent 协作** — 主 Agent 调度，数据分析、图像绘制、理论推导、报告撰写四个子 Agent 各司其职
- **目录权限隔离** — 每个 Agent 只能写入指定目录，防止交叉污染
- **检查点回滚** — 关键节点自动创建检查点，可回滚到任意历史状态
- **交互式调整** — 用户可随时向任意 Agent 发送消息进行干预和优化

### UI/UX（VSCode/Copilot Chat 风格）
- **流式传输** — 实时显示 Agent 输出，逐字流式呈现
- **并排 Agent 面板** — 子 Agent 和主 Agent 面板水平排列，主 Agent 位于最右侧
- **最近项目缓存** — VSCode 风格的最近项目列表，缓存于 `~/.autoreport/recent_projects.json`
- **文件树** — VSCode 风格原生 Qt 实现，22px 行高、16px 图标，简洁标签（Data、References、Theory、Code、Tex）
  - 原生 Qt 样式渲染选择、悬停、分支指示器
  - 支持内联重命名文件/文件夹
  - 拖放导入外部文件
  - 单击文字区域展开/折叠，箭头区域由 Qt 处理
  - 所有目录始终显示展开箭头（VSCode 风格）
- **统一主题系统** — 支持暗色/亮色模式自动检测，基于 VSCode Dark Modern / Light Modern 配色
- **SVG 图标系统** — 使用 VSCode Codicons，高 DPI 显示支持
- **上下文引用栏** — 文件/行选择的可视化指示器，可切换是否包含在消息中
- **对话界面** — Copilot 风格的对话显示，正确的 Markdown 渲染，工具调用按名称分组显示
- **`/clear` 命令** — 在对话中输入 `/clear` 清除历史记录，开始新会话

### UI 特性详情
- **高 DPI 支持** — SVG 图标使用设备像素比渲染，在视网膜显示器上清晰显示
- **智能宽度计算** — Agent 面板和文件树根据内容动态计算最小宽度
- **拖放优化** — 文件拖动预览使用固定大小图标，不会随文件名拉伸
- **编辑体验** — 内联编辑输入框采用灰色背景和蓝色聚焦边框
- **主题适配** — 所有 UI 组件统一使用主题系统，支持暗色/亮色模式自动切换

### 开发工具
- **@ 文件引用** — 在聊天输入中输入 `@` 触发模糊文件搜索，选择文件后插入 Markdown 引用链接
- **选中行上下文** — 在预览面板中选中文本后，上下文自动附加到 Agent 消息中
- **子 Agent 调试模式** — 断开与主 Agent 的通道，独立测试单个 Agent
- **Ctrl+C 退出** — 支持优雅关闭

### LLM 集成
- **多 Provider 支持** — Anthropic、OpenAI、DeepSeek 等，运行时切换模型
- **Provider 预设** — 来自 [cc-switch](https://github.com/farion1231/cc-switch) 的 50+ 服务商预设
- **渐进式提示词加载** — 启动时加载身份，首次激活时加载完整指令（快速启动、丰富上下文）
- **上下文自动压缩** — 接近上下文窗口限制时自动裁剪对话历史

## 快速开始

### 前置依赖

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) 包管理器
- TeX 发行版（TeX Live 或 MiKTeX，用于编译 LaTeX）
- 至少一个 LLM Provider 的 API Key

### 安装

```bash
git clone <repo-url> && cd AutoReport
uv sync --all-extras
```

> **注意**：使用 `--all-extras` 安装开发依赖（pytest、ruff）。生产部署可省略此参数。

### 运行

```bash
autoreport
```

> 如果提示 `autoreport` 命令未找到，请使用 `uv run autoreport` 代替。
>
> 首次启动会提示配置 API 密钥。也可通过环境变量预配置：
>
> ```bash
> export ANTHROPIC_API_KEY="sk-ant-..."
> export OPENAI_API_KEY="sk-..."
> export DEEPSEEK_API_KEY="sk-..."
> autoreport
> ```

## 项目结构

每个实验报告对应一个项目文件夹，固定目录结构：

```
my_experiment/
├── data/            # 原始实验数据（用户放入）+ 分析结果
│   └── processed/   # 数据分析 Agent 仅可写入此目录
├── references/      # 参考资料（PDF、图片）、自定义模板
├── theory/          # 理论推导 Agent 仅可写入此目录
├── code/            # 图像绘制 Agent 仅可写入此目录
└── tex/             # 报告 Agent 仅可写入此目录
```

### Agent 权限

| Agent | 写入目录 | 读取范围 |
|-------|----------------|------------|
| 主 Agent | 仅协调 | 全部目录 |
| 数据分析 | 仅 `data/processed/` | 全部目录 |
| 图像绘制 | 仅 `code/` | 全部目录 |
| 理论推导 | 仅 `theory/` | 全部目录 |
| 报告撰写 | 仅 `tex/` | 全部目录 |
| 用户 | `data/`、`references/` | 全部目录 |

**工具隔离**：每个子 Agent 收到与其写入权限匹配的受限工具子集。Agent 不能修改其指定目录之外的文件。

## 架构

```
autoreport/
├── app.py                 # 入口点：CLI 解析、LoopManager 启动
├── config/                # 基于 Pydantic 的配置（YAML 加载、API 密钥验证）
├── core/
│   ├── loops/            # Agent 运行时：LoopManager、AgentLoop、MessageBus
│   ├── providers/        # LLM Provider 抽象层（工厂、基类）
│   ├── prompts/          # 渐进式提示词加载（身份 → 完整指令）
│   ├── skills.py         # Skill 加载（external/skills/ → Agent 系统提示词）
│   └── tools/            # 工具系统（注册表、文件工具、执行工具、PDF 工具）
├── gui/                  # PyQt6 界面（主窗口、对话框、小部件）
│   ├── theme.py          # 统一主题管理（暗色/亮色模式自动检测）
│   └── widgets/          # 可复用组件
│       ├── file_tree.py      # VSCode 风格文件树（原生 Qt 样式）
│       ├── preview.py        # 预览面板（编辑器/PDF 查看器）
│       ├── agent_panel.py    # Agent 面板（对话、时间线、状态栏）
│       ├── chat_input.py     # 聊天输入框（支持 @ 文件引用）
│       ├── message_row.py    # 消息行渲染（Markdown、工具调用）
│       ├── ui_utils.py       # UI 工具函数（图标、样式助手）
│       └── *.svg             # VSCode Codicons 图标文件
├── interfaces/           # GUI-后台协议（Protocol 定义、消息类型）
├── templates/            # 内置模板（Agent 提示词、报告模板）
│   ├── agents/           # Agent 提示词文件（Markdown）
│   └── reports/          # LaTeX 报告模板（template.tex、default_experiment_report.tex）
├── external/             # Git 忽略的同步内容（预设、技能）
│   ├── cc-switch/        # 来自 cc-switch 仓库的 Provider 预设
│   └── skills/           # Skill Markdown 文件（如 latex-compile.md）
└── utils/                # 日志配置（loguru）
```

### 核心模式

**AgentLoop**：每个 Agent 运行自己的异步循环。通过 LLM 聊天处理消息（带工具定义），然后在最大迭代循环中执行工具调用。

**MessageBus**：异步发布/订阅系统。主 Agent 向子 Agent 发送协调消息；子 Agent 报告问题。用户可以直接向任何 Agent 发送消息。

**调试模式**：子 Agent 断开与主 Agent 消息通道的连接，仅接受直接用户输入。通过 GUI 切换或 `--debug-agent` CLI 参数激活。

**渐进式提示词加载**：Agent 在启动时加载轻量级身份提示词，然后在第一条消息时加载完整指令。之后缓存。

**技能系统**：外部 Markdown 技能（如 `latex-compile`）从 `external/skills/` 加载，根据每个 Agent 的配置注入到系统提示词中。`--sync-presets` 命令也会同步技能仓库中的技能文件。

**报告模板**：报告 Agent 按优先级使用模板：用户 `references/` 目录中的自定义模板 > 内置 `templates/reports/template.tex` > 标准 LaTeX 回退。内置模板支持北大近代物理实验 PKUMpLtX 文档类。

### UI 架构

**主题系统**：`gui/theme.py` 提供统一的颜色管理。自动检测系统暗色/亮色模式（通过 `Qt.ColorScheme` 或调色板亮度回退），提供 VSCode Dark Modern / Light Modern 配色方案。

**文件树组件**：`gui/widgets/file_tree.py` 使用原生 Qt QTreeWidget，通过自定义 delegate 实现全行选择背景和 VSCode 风格的缩进线。支持内联编辑（按 F2 重命名）、拖放导入外部文件。

**Agent 面板**：`gui/widgets/agent_panel.py` 包含对话历史、状态指示器、输入框和调试模式切换。使用流式传输实时显示 Agent 响应。

## 开发

### 运行测试

```bash
uv run pytest -v
```

### 代码检查

```bash
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests
```

### 运行单个测试

```bash
uv run pytest tests/test_agent_loop.py -v
```

## 配置

配置文件：`autoreport.config.yaml`

### Agent 配置

```yaml
agents:
  defaults:
    model: "anthropic/claude-sonnet-4.5"
    provider: "auto"
    max_tokens_policy: "adaptive"
    base_max_tokens: 8192
    retry_max_tokens: 16384
    temperature: 0.1
    max_tool_iterations: 200
```

### Provider 配置

通过 [cc-switch](https://github.com/farion1231/cc-switch) 预设支持 50+ 服务商：

```yaml
providers:
  active: "anthropic-default"
  configurations:
    - name: "Anthropic (Official)"
      provider: "anthropic"
      api_key: null       # 通过 ANTHROPIC_API_KEY 环境变量设置
      default_model: "claude-sonnet-4-20250514"
      enabled: true
```

## 调试模式

子 Agent 支持独立调试模式，可隔离测试单个 Agent。

### 使用方式

**GUI**：点击子 Agent 面板中的"调试模式"按钮。

**CLI**：启动时使用 `--debug-agent` 参数：

```bash
autoreport --debug-agent data_analysis
autoreport --debug-agent data_analysis --debug-agent plotting
```

可选 Agent：`data_analysis`（数据分析）、`plotting`（图像绘制）、`theory`（理论推导）、`report`（报告撰写）

## Agent 提示词

位于 `autoreport/templates/agents/`：

- `main_agent.md` — 动态调度、质量审查清单
- `data_analysis_agent.md` — 数据注释模板、理论对比
- `plotting_agent.md` — 图像注释模板、自验证
- `theory_agent.md` — 公式元数据模板
- `report_agent.md` — 完整性检查、模板优先级、叙述风格（基于教材写作原则增强）

## 技能系统

技能是存放在 `external/skills/` 中的 Markdown 文件，提供领域特定指令，注入到 Agent 的系统提示词中。当前已启用：

- **latex-compile**（报告 Agent）— XeLaTeX 编译流程、错误诊断、两遍编译

## MinerU 集成

[MinerU](https://mineru.net/) CLI 用于 PDF 解析。

### 设置

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api auth
```

## 参考项目

- [cc-switch](https://github.com/farion1231/cc-switch) — Provider 预设（50+ 服务商）
- [DeepCode](../DeepCode) — API 配置、多 provider 支持、错误处理
- [nanobot](../nanobot) — AgentLoop 架构、工具定义
- [codex](../codex) — UI 设计模式、流式传输实现
- [TradingAgents](../TradingAgents) — 多 Agent 协调、共享状态、条件边
- [Codex](../Codex) — 迭代 Agent 循环、"持续运行直到完成"模式、进度追踪

## 许可证

MIT License
