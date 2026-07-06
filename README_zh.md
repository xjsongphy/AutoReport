<div align="center">

![title](assets/screenshots/title.png)

### 基于多 Agent 协作的自动化物理实验报告撰写系统

[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#)
[![Python](https://img.shields.io/badge/python-%E2%89%A5%203.12-blue.svg)](https://www.python.org/)
[![Built with PyQt6](https://img.shields.io/badge/built%20with-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) | 中文

</div>

---

基于多 Agent 协作的自动化物理实验报告撰写系统。用户提供实验数据和参考资料，Agent 团队通过理论推导、数据分析、可视化绘图和 LaTeX 排版，自动生成完整的实验报告。

## 功能特性

### 核心能力
- **多 Agent 协作** — 主 Agent 调度，数据分析、图像绘制、理论推导、报告撰写四个子 Agent 各司其职
- **目录权限隔离** — 每个 Agent 只能写入指定目录，防止交叉污染
- **任务清单跟踪** — 结构化任务委派，waitlist 与 todolist 链式关联，完成时自动通知
- **检查点回滚** — 关键节点自动创建检查点，可回滚到任意历史状态
- **交互式调整** — 用户可随时向任意 Agent 发送消息进行干预和优化

### UI/UX（VSCode/Copilot Chat 风格）
- **流式传输** — 实时显示 Agent 输出，逐字流式呈现
- **可切换 Agent 面板** — 单个 Agent 聊天面板，顶部下拉选择器在 Main / Data Analysis / Plotting / Theory / Report 之间切换
- **最近项目缓存** — VSCode 风格的最近项目列表，缓存于 `~/.autoreport/recent_projects.json`
- **文件树** — VSCode 风格文件树，22px 行高、16px 图标，简洁标签（Data、References、Theory、Plots、Outline、Tex）
- **上下文引用栏** — 文件/行选择的可视化指示器，可切换是否包含在消息中
- **对话界面** — Copilot 风格的对话显示，正确的 Markdown 渲染，工具调用按名称分组显示
- **斜杠命令** — `/clear`、`/new`、`/help`、`/compact`、`/init`

### 开发工具
- **@ 文件引用** — 在聊天输入中输入 `@` 触发模糊搜索，选择文件后插入 Markdown 引用链接
- **选中行上下文** — 在预览面板中选中的文本会自动附加到 Agent 消息中
- **子 Agent 调试模式** — 断开与主 Agent 的通道，独立测试单个 Agent

### LLM 集成
- **多 Provider 支持** — Anthropic、OpenAI、DeepSeek 等，运行时切换模型
- **Provider 预设** — 来自 [cc-switch](https://github.com/farion1231/cc-switch) 的 50+ 服务商模板
- **上下文自动压缩** — 接近上下文窗口限制时自动裁剪对话历史

## 主工作区

主工作区把项目文件树、文档预览和 Agent 对话时间线放在同一窗口中。用户可以查看生成的 LaTeX/PDF 输出，同时继续与 Agent 团队交互。

![AutoReport 主工作区](assets/screenshots/main-window.png)

## 快速开始

**前置依赖：** Python >= 3.12、[uv](https://docs.astral.sh/uv/) 包管理器、TeX 发行版、至少一个 LLM Provider 的 API Key。

```bash
git clone https://github.com/xjsongphy/AutoReport && cd AutoReport
uv sync
```

运行：

```bash
autoreport
```

启动窗口用于打开已有实验文件夹、新建项目、配置 API Provider，或从最近项目列表恢复工作。

![AutoReport 启动窗口](assets/screenshots/start-window.png)

首次启动会提示配置 API。也可通过环境变量预配置：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
autoreport
```

## MinerU 集成

AutoReport 使用 [mineru-open-api](https://github.com/opendatalab/MinerU) CLI 解析 PDF（支持 PDF、图片、DOCX、PPTX、XLSX → Markdown）。

**安装：**

1. 安装 mineru-open-api：
   ```bash
   curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
   ```
   详见 [mineru-open-api 文档](https://mineru.net/ecosystem?tab=cli)。

2. 在 [MinerU](https://mineru.net/apiManage/token) 注册获取 API Key，然后认证：
   ```bash
   mineru-open-api auth
   ```

3. 应用启动时自动检测可用性，未安装会给出警告。

支持批量处理（单文件上限 200MB / 600 页），可提取文本/图片/表格/公式。

## 配置

配置文件：`autoreport.config.yaml`

API 配置对话框用于管理 Provider 预设、当前 Provider 选择、API 密钥、Base URL 和默认模型。

![AutoReport API 配置](assets/screenshots/configuration-window.png)

```yaml
agents:
  defaults:
    model: "anthropic/claude-sonnet-4.5"
    temperature: 0.1
    max_tool_iterations: 200
```

## 调试模式

```bash
autoreport --debug-agent data_analysis
autoreport --debug-agent data_analysis --debug-agent plotting
```

可选 Agent：`data_analysis`、`plotting`、`theory`、`report`

## 项目结构

```
my_experiment/
├── Data/            # 原始实验数据（用户放入）+ 分析结果
│   └── Processed/   # 数据分析 Agent 仅可写入此目录
├── References/      # 参考资料（PDF、图片）、自定义模板
├── Theory/          # 理论推导 Agent 仅可写入此目录
├── Plots/           # 图像绘制 Agent 仅可写入此目录
│   ├── Fig/         # 生成的图像
│   └── Scripts/     # 绘图脚本
├── Outline/         # 主 Agent 撰写报告大纲与路由记录
└── Tex/             # 报告 Agent 仅可写入此目录
```

### Agent 权限

| Agent | 写入目录 | 读取范围 |
|-------|----------------|------------|
| 主 Agent | `Outline/` | 全部目录 |
| 数据分析 | `Data/Processed/` | 全部目录 |
| 图像绘制 | `Plots/` | 全部目录 |
| 理论推导 | `Theory/` | 全部目录 |
| 报告撰写 | `Tex/` | 全部目录 |
| 用户 | `Data/`、`References/` | 全部目录 |

## 架构

```
autoreport/
├── app.py                 # 入口点：CLI 解析、LoopManager 启动
├── config/                # 基于 Pydantic 的配置（YAML 加载、API 密钥验证）
├── core/
│   ├── loops/            # Agent 运行时：LoopManager、AgentLoop、MessageBus
│   ├── providers/        # LLM Provider 抽象层（工厂、基类）
│   ├── prompts/          # 渐进式提示词加载（身份 → 完整指令）
│   ├── tools/            # 工具系统（注册表、文件工具、执行工具、PDF 工具、技能工具）
│   ├── checkpoints.py    # 基于操作日志的检查点，支持可逆文件操作回滚
│   ├── conversations.py  # 多会话对话存储
│   ├── file_search.py    # @ 引用的模糊文件搜索
│   ├── preset_sync.py    # cc-switch 预设同步
│   └── recent_projects.py# 最近项目缓存
├── gui/                  # PyQt6 界面（主窗口、对话框、小部件）
│   └── widgets/          # 可复用组件（文件树、预览、Agent 面板）
├── interfaces/           # GUI-后台协议（Protocol 定义、消息类型）
├── resources/            # 内置资源
├── templates/            # 内置模板（Agent 提示词、报告模板）
│   ├── agents/           # Agent 提示词文件（Markdown）
│   └── reports/          # LaTeX 报告模板
├── external/             # Git 忽略的同步内容（预设、技能）
│   ├── cc-switch/        # 来自 cc-switch 仓库的 Provider 预设
│   └── skills/           # Skill Markdown 文件
└── utils/                # 日志配置（loguru）
```

## 开发

```bash
# 运行测试
uv run pytest -v

# 代码检查
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests

# 覆盖率
uv run pytest --cov=autoreport --cov-report=html
```

## UI 图标

Agent 类型图标来自 [Tabler Icons](https://tabler-icons.io/) — 6000+ 免费 SVG 图标，MIT License。

## 参考项目

- [DeepCode](https://github.com/HKUDS/DeepCode) — API 配置、多 provider 支持、错误处理
- [cc-switch](https://github.com/farion1231/cc-switch) — Provider 预设（50+ 服务商）
- [nanobot](https://github.com/HKUDS/nanobot) — AgentLoop 架构、工具定义、compact/命令系统
- [codex](https://github.com/openai/codex) — UI 设计模式、流式传输实现
- [openclaw](https://github.com/openclaw/openclaw) — 个人 AI 助手、技能系统、多渠道 Agent 设计
- [VS Code](https://github.com/microsoft/vscode) — 编辑器 UI/UX 模式、面板布局、命令与扩展架构
- [Claude Code](https://claude.com/claude-code) — Agent 聊天面板 UI/UX（气泡消息、工具调用分组、流式输出、`@` 引用、斜杠命令）
- [PKUMpLtX](https://github.com/CastleStar14654/PKUMpLtX) — 内置 LaTeX 报告模板来源（北大近代物理实验，基于 revtex4-2）

### Star History

[![Star History Chart](https://api.star-history.com/chart?repos=xjsongphy/AutoReport&type=date&legend=top-left)](https://www.star-history.com/?repos=xjsongphy%2FAutoReport&type=date&legend=top-left)

## 许可证

MIT License
