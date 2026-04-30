# AutoReport

基于多 Agent 协作的自动化物理实验报告撰写系统。用户提供实验数据和参考资料，Agent 团队通过理论推导、数据分析、可视化绘图和 LaTeX 排版，自动生成完整的实验报告。

## 功能特性

- **多 Agent 协作** — 主 Agent 调度，数据分析、图像绘制、理论推导、报告撰写四个子 Agent 各司其职
- **多 Provider 支持** — Anthropic、OpenAI、DeepSeek 等，运行时可切换模型，切换 Provider 支持 Restart
- **目录权限隔离** — 每个 Agent 只能写入指定目录，防止交叉污染
- **检查点回滚** — 关键节点自动创建检查点，可回滚到任意历史状态
- **@ 文件引用** — 在聊天输入中输入 `@` 触发模糊文件搜索，选择文件后插入 Markdown 引用链接
- **选中行上下文** — 在预览面板中选中文本后，上下文自动附加到 Agent 消息中
- **子 Agent 调试模式** — 断开与主 Agent 的通道，独立测试单个 Agent
- **交互式调整** — 用户可随时向任意 Agent 发送消息进行干预和优化

## 快速开始

### 前置依赖

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) 包管理器
- TeX 发行版（如 TeX Live 或 MiKTeX，用于编译 LaTeX）
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

首次启动会提示配置 API 密钥。也可通过环境变量预配置：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
autoreport
```

## 项目结构

每个实验报告对应一个项目文件夹，固定目录结构：

```
my_experiment/
├── data/            # 原始实验数据（用户放入）+ 分析结果
│   └── processed/   # 数据分析 Agent 输出
├── references/      # 参考资料（PDF、图片）、自定义模板
├── theory/          # 理论推导 Agent 输出
├── code/            # 图像绘制 Agent 的代码和图片
└── tex/             # 报告 Agent 的 LaTeX 源码和编译产物
```

### Agent 权限

| Agent | 写入目录 | 读取范围 |
|-------|---------|---------|
| 数据分析 | `data/processed/` | 全部 |
| 图像绘制 | `code/` | 全部 |
| 理论推导 | `theory/` | 全部 |
| 报告撰写 | `tex/` | 全部 |
| 用户 | `data/`、`references/` | 全部 |

## 架构

```
autoreport/
├── config/          # 配置管理（Pydantic Settings + YAML）
├── core/
│   ├── loops/       # Agent Loop、消息总线、Agent 管理器
│   ├── providers/   # LLM Provider 抽象层（Anthropic/OpenAI/DeepSeek）
│   ├── prompts/     # Agent 提示词模板（支持渐进式加载）
│   └── tools/       # 工具集（文件操作、Shell 执行、PDF 解析）
├── gui/             # PyQt6 界面（主窗口、项目对话框、配置对话框）
│   └── widgets/     # 可复用组件（文件树、预览、Agent 面板）
├── interfaces/      # GUI-后台通信协议（Protocol + 消息类型）
├── utils/           # 日志配置（loguru）
├── templates/       # 内置模板（Agent 提示词、报告模板）
└── app.py           # 入口点
```

GUI 与后台通过 `interfaces` 层解耦：定义了 `GUIAPI` / `BackendAPI` Protocol 和消息类型，双方通过异步消息总线通信。

## 开发

首先确保已安装开发依赖：

```bash
uv sync --all-extras
```

### 运行测试

```bash
uv run pytest -v
```

### 代码检查

```bash
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests   # 自动修复
```

### 运行单个测试

```bash
uv run pytest tests/test_config.py -v
uv run pytest tests/test_file_tools.py::test_read_file -v
```

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.12 |
| 包管理 | uv + hatchling |
| GUI | PyQt6 |
| LLM | 原生 SDK（anthropic / openai） |
| 配置 | pydantic-settings + YAML |
| 日志 | loguru |
| 数据处理 | pandas, matplotlib |
| LaTeX 编译 | xelatex / lualatex（系统安装） |
| PDF 解析 | mineru-open-api（外部服务） |

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
    retry_max_tokens: 16384  # 复杂任务重试时增大输出
    temperature: 0.1
    max_tool_iterations: 200
    timezone: "Asia/Shanghai"
    prompt_templates_dir: "templates/agents"
    context_window_tokens: 200000
```

### MinerU API 配置

```yaml
mineru_api:
  url: "http://localhost:9999"
  enabled: true
  timeout: 300
  validate_on_startup: true  # 不可用时显示软警告
```

### Provider 配置

```yaml
providers:
  anthropic:
    api_key: null  # 通过 ANTHROPIC_API_KEY 环境变量设置
    api_base: null
  openai:
    api_key: null  # 通过 OPENAI_API_KEY 环境变量设置
    api_base: null
  deepseek:
    api_key: null  # 通过 DEEPSEEK_API_KEY 环境变量设置
    api_base: "https://api.deepseek.com/v1"
```

## 调试模式

子 Agent 支持独立调试模式，可以隔离测试单个 Agent 的工具和输出。

### 调试模式行为

| 行为 | 正常模式 | 调试模式 |
|------|---------|---------|
| 主 Agent 协调命令 | 接受 | **忽略** |
| 用户直接输入 | 接受 | 接受 |
| 状态显示 | 正常 | 显示"调试模式"（紫色） |
| 消息上下文 | 正常 | 注入 `[调试模式]` 前缀 |

### 使用方式

**GUI**: 点击子 Agent 面板中的"调试模式"按钮，按钮变红即启用。

**CLI**: 启动时使用 `--debug-agent` 参数（可重复使用）：

```bash
# 以调试模式启动数据分析 Agent
autoreport --debug-agent data_analysis

# 以调试模式启动多个 Agent
autoreport --debug-agent data_analysis --debug-agent plotting
```

可选 Agent 名称：`data_analysis`（数据分析）、`plotting`（图像绘制）、`theory`（理论推导）、`report`（报告撰写）

### 示例

数据分析 Agent 处于调试模式时，首条消息会收到上下文提示：

```
[调试模式] 此 Agent 处于独立调试模式，不与其他 Agent 通信。
你可以直接测试此 Agent 的工具和输出。

请分析 data/experiment_1.csv 中的数据
```

## Agent 提示词

AutoReport 使用渐进式加载系统管理 Agent 提示词：

- **Identity**（启动时加载）：简要角色定义（约 100-200 词）
- **Full Instructions**（首次激活时加载）：详细工作流程、参考资料处理、叙述风格、输出格式

提示词模板位于 `autoreport/templates/agents/`：
- `main_agent.md` - 主协调 Agent
- `data_analysis_agent.md` - 数据处理和分析
- `plotting_agent.md` - 数据可视化
- `theory_agent.md` - 理论推导
- `report_agent.md` - LaTeX 报告撰写

## 报告模板

内置报告模板位于 `autoreport/templates/reports/`：

- `default_experiment_report.tex` - 标准物理实验报告模板
- `requirements.md` - 叙述风格和格式指南
- `README.md` - 模板文档

用户可以通过在 `project/references/` 中放置自定义模板来覆盖内置模板。

**优先级**：用户模板 > 内置模板 > 标准 LaTeX

## MinerU Open API 集成

AutoReport 使用 [mineru-open-api](https://github.com/opendatalab/MinerU) 进行 PDF 解析。

### 设置

1. 安装并启动 mineru-open-api 服务：
```bash
pip install mineru-open-api
mineru-open-api --port 9999
```

2. 在 `autoreport.config.yaml` 中配置：
```yaml
mineru_api:
  url: "http://localhost:9999"
  enabled: true
  timeout: 300
```

3. 启动时如果 API 不可用，系统会显示软警告，但仍允许应用运行。

### 功能

- 将 PDF 参考资料转换为 Markdown
- 提取文本、图片和表格
- 支持多页文档
- 异步处理，5 分钟超时

## 参与贡献

欢迎贡献！请随时提交问题或拉取请求。

## 参考项目

- [DeepCode](../DeepCode) — API 配置方式（YAML secrets + 环境变量回退）、多 provider 支持、错误处理和重试机制、循环检测
- [nanobot](../nanobot) — AgentLoop 核心架构、工具定义、多 provider 原生 SDK 调用、compact/命令系统、Pydantic 配置 schema

## 许可证

MIT License - 详见 LICENSE 文件
