# AutoReport

基于多 Agent 协作的自动化物理实验报告撰写系统。用户提供实验数据和参考资料，Agent 团队通过理论推导、数据分析、可视化绘图和 LaTeX 排版，自动生成完整的实验报告。

## 功能特性

- **多 Agent 协作** — 主 Agent 调度，数据分析、图像绘制、理论推导、报告撰写四个子 Agent 各司其职
- **多 Provider 支持** — Anthropic、OpenAI、DeepSeek 等，运行时可切换模型，切换 Provider 支持 Restart
- **目录权限隔离** — 每个 Agent 只能写入指定目录，防止交叉污染
- **检查点回滚** — 关键节点自动创建检查点，可回滚到任意历史状态
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
uv sync
```

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
│   └── tools/       # 工具集（文件操作、Shell 执行、PDF 解析）
├── gui/             # PyQt6 界面（主窗口、项目对话框、配置对话框）
│   └── widgets/     # 可复用组件（文件树、预览、Agent 面板）
├── interfaces/      # GUI-后台通信协议（Protocol + 消息类型）
├── utils/           # 日志配置（loguru）
└── app.py           # 入口点
```

GUI 与后台通过 `interfaces` 层解耦：定义了 `GUIAPI` / `BackendAPI` Protocol 和消息类型，双方通过异步消息总线通信。

## 开发

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
