# AutoReport

[English](#english) | [中文](#中文)

---

## English

### Overview

A multi-agent collaborative automated physics experiment report writing system. Users provide experimental data and reference materials, then agents collaboratively generate LaTeX reports through theoretical derivation, data analysis, visualization, and typesetting.

### Features

#### Core Capabilities
- **Multi-Agent Collaboration** — Main Agent orchestrates, with four sub-agents (Data Analysis, Plotting, Theory, Report) each specializing in their domain
- **Directory Permission Isolation** — Each agent can only write to designated directories, preventing cross-contamination
- **Waitlist/Todolist Tracking** — Structured task delegation with linked waitlist-todolist chains and auto-notification on completion
- **Checkpoint Rollback** — Automatically creates checkpoints at key nodes; roll back to any historical state
- **Interactive Adjustment** — Users can message any agent at any time for intervention and optimization

#### UI/UX (VSCode/Copilot Chat Style)
- **Streaming Responses** — Real-time agent output, word-by-word streaming
- **Side-by-Side Agent Panels** — Sub Agent and Main Agent panels arranged horizontally
- **Recent Projects Cache** — VSCode-style recent projects list, cached in `~/.autoreport/recent_projects.json`
- **File Explorer** — VSCode-style file tree with 22px row height, 16px icons, concise labels (Data, References, Theory, Code, Tex)
- **Context Chip Bar** — Visual indicator for file/line selections with toggle to include/exclude from messages
- **Chat Interface** — Copilot-style conversation display with proper Markdown rendering and grouped tool calls
- **Slash Commands** — `/clear`, `/new`, `/help`, `/compact`, `/init`

#### Developer Tools
- **@ File References** — Type `@` in chat to fuzzy-search and insert file references as Markdown links
- **Selected Line Context** — Text selections in preview pane are automatically appended to agent messages
- **Sub-Agent Debug Mode** — Disconnect from Main Agent channel, test individual agents independently

#### LLM Integration
- **Multi-Provider Support** — Anthropic, OpenAI, DeepSeek, etc. Runtime model switching
- **Provider Presets** — 50+ provider templates from [cc-switch](https://github.com/farion1231/cc-switch)
- **Progressive Prompt Loading** — Identity at startup, full instructions on first activation (fast startup, rich context)
- **Context Auto-Compact** — Automatically trims conversation history when approaching context window limits

### Quick Start

**Prerequisites:** Python >= 3.12, [uv](https://docs.astral.sh/uv/) package manager, TeX distribution, at least one LLM Provider API key.

```bash
git clone https://github.com/xjsongphy/AutoReport && cd AutoReport
uv sync --all-extras
```

Run:

```bash
autoreport
```

First launch prompts for API configuration. Pre-configure via environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
autoreport
```

### Project Structure

```
my_experiment/
├── data/            # Raw experimental data (user input) + analysis results
│   └── processed/   # Data Analysis Agent output only
├── references/      # Reference materials (PDF, images), custom templates
├── theory/          # Theory Agent output only
├── code/            # Plotting Agent code and generated images
└── tex/             # Report Agent LaTeX source and compiled output
```

#### Agent Permissions

| Agent | Write Directory | Read Scope |
|-------|----------------|------------|
| Main Agent | coordinates only | All directories |
| Data Analysis | `data/processed/` | All directories |
| Plotting | `code/` | All directories |
| Theory | `theory/` | All directories |
| Report | `tex/` | All directories |
| User | `data/`, `references/` | All directories |

### Architecture

```
autoreport/
├── app.py                 # Entry point: CLI parsing, LoopManager startup
├── config/                # Pydantic-based config (YAML loading, API key validation)
├── core/
│   ├── loops/            # Agent runtime: LoopManager, AgentLoop, MessageBus
│   ├── providers/        # LLM provider abstraction (factory, base classes)
│   ├── prompts/          # Progressive prompt loading (identity → full instructions)
│   ├── tools/            # Tool system (registry, file tools, exec tools, PDF tool)
│   ├── checkpoints.py    # File-state checkpoint with hash tracking and rollback
│   ├── conversations.py  # Multi-session conversation store
│   ├── file_search.py    # Fuzzy file search for @ references
│   ├── preset_sync.py    # cc-switch preset synchronization
│   ├── recent_projects.py# Recent projects cache
│   └── skills.py         # Skill loader (external/skills/ → agent system prompt)
├── gui/                  # PyQt6 interface (main window, dialogs, widgets)
│   └── widgets/          # Reusable components (file tree, preview, agent panel)
├── interfaces/           # GUI-backend protocol (protocol definitions, message types)
├── resources/            # Built-in resources
├── templates/            # Built-in templates (agent prompts, report templates)
│   ├── agents/           # Agent prompt files (Markdown)
│   └── reports/          # LaTeX report templates
├── external/             # Git-ignored synced content (presets, skills)
│   ├── cc-switch/        # Provider presets from cc-switch repo
│   └── skills/           # Skill Markdown files
└── utils/                # Logging configuration (loguru)
```

### Development

```bash
# Run tests
uv run pytest -v

# Lint
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests

# Run with coverage
uv run pytest --cov=autoreport --cov-report=html
```

### Configuration

Configuration file: `autoreport.config.yaml`

```yaml
agents:
  defaults:
    model: "anthropic/claude-sonnet-4.5"
    temperature: 0.1
    max_tool_iterations: 200
```

### Debug Mode

```bash
autoreport --debug-agent data_analysis
autoreport --debug-agent data_analysis --debug-agent plotting
```

Valid agents: `data_analysis`, `plotting`, `theory`, `report`

### MinerU Integration

AutoReport uses [mineru-open-api](https://github.com/opendatalab/MinerU) CLI for PDF parsing (PDF, images, DOCX, PPTX, XLSX → Markdown).

**Setup:**

1. Install mineru-open-api:
   ```bash
   curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
   ```
   See [mineru-open-api docs](https://mineru.net/ecosystem?tab=cli) for details.

2. Register at [MinerU](https://mineru.net/apiManage/token) for an API key, then authenticate:
   ```bash
   mineru-open-api auth
   ```

3. The app auto-detects availability on startup and shows a warning if not installed.

Supports batch processing (max 200MB / 600 pages per file), text/image/table/formula extraction.

### Reference Projects

- [cc-switch](https://github.com/farion1231/cc-switch) — Provider presets (50+ providers)
- [nanobot](https://github.com/nanobot) — AgentLoop architecture, tool definitions
- [codex](https://github.com/codex) — UI design patterns, streaming implementation

### License

MIT License

---

## 中文

### 概述

基于多 Agent 协作的自动化物理实验报告撰写系统。用户提供实验数据和参考资料，Agent 团队通过理论推导、数据分析、可视化绘图和 LaTeX 排版，自动生成完整的实验报告。

### 功能特性

#### 核心能力
- **多 Agent 协作** — 主 Agent 调度，数据分析、图像绘制、理论推导、报告撰写四个子 Agent 各司其职
- **目录权限隔离** — 每个 Agent 只能写入指定目录，防止交叉污染
- **Waitlist/Todolist 任务追踪** — 结构化任务委托，关联式 waitlist-todolist 链，完成时自动通知
- **检查点回滚** — 关键节点自动创建检查点，可回滚到任意历史状态
- **交互式调整** — 用户可随时向任意 Agent 发送消息进行干预和优化

#### UI/UX（VSCode/Copilot Chat 风格）
- **流式传输** — 实时显示 Agent 输出，逐字流式呈现
- **并排 Agent 面板** — 子 Agent 和主 Agent 面板水平排列
- **最近项目缓存** — VSCode 风格的最近项目列表，缓存于 `~/.autoreport/recent_projects.json`
- **资源管理器** — VSCode 风格文件树，22px 行高、16px 图标，简洁标签（Data、References、Theory、Code、Tex）
- **上下文引用栏** — 文件/行选择的可视化指示器，可切换是否包含在消息中
- **对话界面** — Copilot 风格的对话显示，Markdown 渲染，工具调用分组展示
- **斜杠命令** — `/clear`、`/new`、`/help`、`/compact`、`/init`

#### 开发工具
- **@ 文件引用** — 输入 `@` 触发模糊文件搜索，选择后插入 Markdown 引用链接
- **选中行上下文** — 在预览面板中选中文本后，上下文自动附加到 Agent 消息中
- **子 Agent 调试模式** — 断开与主 Agent 的通道，独立测试单个 Agent

#### LLM 集成
- **多 Provider 支持** — Anthropic、OpenAI、DeepSeek 等，运行时切换模型
- **Provider 预设** — 来自 [cc-switch](https://github.com/farion1231/cc-switch) 的 50+ 服务商预设
- **渐进式提示词加载** — 启动时加载身份，首次激活时加载完整指令（快速启动、丰富上下文）
- **上下文自动压缩** — 接近上下文窗口限制时自动裁剪对话历史

### 快速开始

**前置依赖：** Python >= 3.12，[uv](https://docs.astral.sh/uv/) 包管理器，TeX 发行版，至少一个 LLM Provider 的 API Key。

```bash
git clone <repo-url> && cd AutoReport
uv sync --all-extras
```

运行：

```bash
autoreport
```

首次启动会提示配置 API 密钥。可通过环境变量预配置：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
autoreport
```

### 项目结构

```
my_experiment/
├── data/            # 原始实验数据（用户放入）+ 分析结果
│   └── processed/   # 数据分析 Agent 仅可写入此目录
├── references/      # 参考资料（PDF、图片）、自定义模板
├── theory/          # 理论推导 Agent 仅可写入此目录
├── code/            # 图像绘制 Agent 仅可写入此目录
└── tex/             # 报告 Agent 仅可写入此目录
```

#### Agent 权限

| Agent | 写入目录 | 读取范围 |
|-------|---------|---------|
| 主 Agent | 仅协调 | 全部目录 |
| 数据分析 | 仅 `data/processed/` | 全部目录 |
| 图像绘制 | 仅 `code/` | 全部目录 |
| 理论推导 | 仅 `theory/` | 全部目录 |
| 报告撰写 | 仅 `tex/` | 全部目录 |
| 用户 | `data/`、`references/` | 全部目录 |

### 架构

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
│   └── widgets/          # 可复用组件（文件树、预览、Agent 面板）
├── interfaces/           # GUI-后台协议（Protocol 定义、消息类型）
├── templates/            # 内置模板（Agent 提示词、报告模板）
│   ├── agents/           # Agent 提示词文件（Markdown）
│   └── reports/          # LaTeX 报告模板
├── external/             # Git 忽略的同步内容（预设、技能）
│   ├── cc-switch/        # 来自 cc-switch 仓库的 Provider 预设
│   └── skills/           # Skill Markdown 文件
└── utils/                # 日志配置（loguru）
```

### 开发

```bash
# 运行测试
uv run pytest -v

# 代码检查
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests

# 覆盖率
uv run pytest --cov=autoreport --cov-report=html
```

### 配置

配置文件：`autoreport.config.yaml`

```yaml
agents:
  defaults:
    model: "anthropic/claude-sonnet-4.5"
    temperature: 0.1
    max_tool_iterations: 200
```

### 调试模式

```bash
autoreport --debug-agent data_analysis
autoreport --debug-agent data_analysis --debug-agent plotting
```

可选 Agent：`data_analysis`（数据分析）、`plotting`（图像绘制）、`theory`（理论推导）、`report`（报告撰写）

### MinerU 集成

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api auth
```

### 参考项目

- [cc-switch](https://github.com/farion1231/cc-switch) — Provider 预设（50+ 服务商）
- [nanobot](https://github.com/nanobot) — AgentLoop 架构、工具定义
- [codex](https://github.com/codex) — UI 设计模式、流式传输实现

### 许可证

MIT License
