# AutoReport

[中文](README_zh.md)

An automated physics experiment report writing system based on multi-agent collaboration. Users provide experimental data and reference materials, then agents collaboratively generate LaTeX reports through theoretical derivation, data analysis, visualization, and typesetting.

## Features

- **Multi-Agent Collaboration** — Main Agent orchestrates, with four sub-agents (data analysis, plotting, theory, report) each specializing in their domain
- **Multi-Provider Support** — Anthropic, OpenAI, DeepSeek, etc. Runtime model switching, provider switch requires restart
- **Directory Permission Isolation** — Each agent can only write to designated directories, preventing cross-contamination
- **Checkpoint Rollback** — Automatically creates checkpoints at key nodes, can rollback to any historical state
- **@ File References** — Type `@` in chat to fuzzy-search and insert file references as markdown links
- **Selected Line Context** — Text selections in the preview pane are automatically appended to agent messages
- **Sub-Agent Debug Mode** — Disconnect from Main Agent channel, test individual agents independently
- **Interactive Adjustment** — Users can send messages to any agent at any time for intervention and optimization

## Quick Start

### Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- TeX distribution (TeX Live or MiKTeX for LaTeX compilation)
- At least one LLM Provider API key

### Installation

```bash
git clone <repo-url> && cd AutoReport
uv sync --all-extras
```

> **Note**: Use `--all-extras` to install development dependencies (pytest, ruff). For production deployment, omit this flag.

### Running

```bash
autoreport
```

> If `autoreport` command is not found, use `uv run autoreport` instead, or activate the virtual environment first: `source .venv/bin/activate` (Linux/macOS) or `.\.venv\Scripts\Activate.ps1` (Windows).
>
> **Auto-activation (optional)**: Add the following to your shell profile to automatically activate `.venv` when entering the project directory:
>
> **PowerShell** (`$PROFILE`):
> ```powershell
> Remove-Item Alias:cd -ErrorAction SilentlyContinue
> function cd($path) {
>     Set-Location $path
>     $a = ".\.venv\Scripts\Activate.ps1"
>     if (Test-Path $a) { . $a }
> }
> $initialActivate = ".\.venv\Scripts\Activate.ps1"
> if (Test-Path $initialActivate) { . $initialActivate }
> ```
>
> **Bash/Zsh** (`~/.bashrc` / `~/.zshrc`):
> ```bash
> cd() { builtin cd "$@" && [ -f .venv/bin/activate ] && . .venv/bin/activate; }
> ```

On first launch, you'll be prompted to configure API keys. You can also pre-configure via environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
autoreport
```

## Project Structure

Each experiment report corresponds to a project folder with a fixed directory structure:

```
my_experiment/
├── data/            # Raw experimental data (user input) + analysis results
│   └── processed/   # Data Analysis Agent output
├── references/      # Reference materials (PDF, images), custom templates
├── theory/          # Theory Agent output
├── code/            # Plotting Agent code and generated images
└── tex/             # Report Agent LaTeX source and compiled output
```

### Agent Permissions

| Agent | Write Directory | Read Scope |
|-------|----------------|------------|
| Data Analysis | `data/processed/` | All |
| Plotting | `code/` | All |
| Theory | `theory/` | All |
| Report | `tex/` | All |
| User | `data/`, `references/` | All |

## Architecture

```
autoreport/
├── config/          # Configuration management (Pydantic Settings + YAML)
├── core/
│   ├── loops/       # Agent Loop, message bus, agent manager
│   ├── providers/   # LLM Provider abstraction layer
│   ├── prompts/     # Agent prompt templates with progressive loading
│   └── tools/       # Tool set (file operations, shell execution, PDF parsing)
├── gui/             # PyQt6 interface (main window, dialogs, widgets)
├── interfaces/      # GUI-backend communication protocol
├── utils/           # Logging configuration (loguru)
├── templates/       # Built-in templates (agent prompts, report templates)
└── app.py           # Entry point
```

GUI and backend are decoupled through the `interfaces` layer: defining `GUIAPI`/`BackendAPI` protocols and message types, communicating via an asynchronous message bus.

## Development

First, ensure development dependencies are installed:

```bash
uv sync --all-extras
```

### Run Tests

```bash
uv run pytest -v
```

### Code Linting

```bash
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests   # Auto-fix
```

### Run Single Test

```bash
uv run pytest tests/test_config.py -v
uv run pytest tests/test_file_tools.py::test_read_file -v
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12 |
| Package Management | uv + hatchling |
| GUI | PyQt6 |
| LLM | Native SDK (anthropic / openai) |
| Configuration | pydantic-settings + YAML |
| Logging | loguru |
| Data Processing | pandas, matplotlib |
| LaTeX Compilation | xelatex / lualatex (system installed) |
| PDF Parsing | mineru-open-api (external service) |

## Configuration

Configuration file: `autoreport.config.yaml`

### Agent Configuration

```yaml
agents:
  defaults:
    model: "anthropic/claude-sonnet-4.5"
    provider: "auto"
    max_tokens_policy: "adaptive"
    base_max_tokens: 8192
    retry_max_tokens: 16384  # Increase on retry for complex tasks
    temperature: 0.1
    max_tool_iterations: 200
    timezone: "Asia/Shanghai"
    prompt_templates_dir: "templates/agents"
    context_window_tokens: 200000
```

### Provider Configuration

Supports multiple API configurations with preset templates from [cc-switch](https://github.com/farion1231/cc-switch) (50+ providers including Anthropic, DeepSeek, OpenRouter, ZhiPu, etc.).

```yaml
providers:
  active: "anthropic-default"  # Active config ID
  configurations:
    - name: "Anthropic (Official)"
      provider: "anthropic"
      api_key: null       # Set via ANTHROPIC_API_KEY env var
      api_base: null
      default_model: "claude-sonnet-4-20250514"
      enabled: true

    - name: "DeepSeek"
      provider: "deepseek"
      api_key: null       # Set via DEEPSEEK_API_KEY env var
      api_base: "https://api.deepseek.com"
      default_model: "deepseek-chat"
      enabled: true
```

First launch opens a GUI config dialog with preset templates. You can also use environment variables for API keys.

## Debug Mode

Sub-agents support standalone debug mode for isolated testing of individual agent tools and outputs.

### What Debug Mode Does

| Behavior | Normal | Debug Mode |
|----------|--------|------------|
| Main Agent coordination | Accepted | **Ignored** |
| Direct user input | Accepted | Accepted |
| Status reporting | Normal | Shows "Debug Mode" indicator |
| Message context | Normal | `[Debug Mode]` prefix injected |

### Usage

**GUI**: Click the "Debug Mode" button in the sub-agent panel. The button turns red when active.

**CLI**: Start with `--debug-agent` (repeatable):

```bash
# Start with Data Analysis agent in debug mode
autoreport --debug-agent data_analysis

# Start with multiple agents in debug mode
autoreport --debug-agent data_analysis --debug-agent plotting
```

Valid agent names: `data_analysis`, `plotting`, `theory`, `report`

### Example

With Data Analysis agent in debug mode, the first message receives context:

```
[Debug Mode] This agent is in standalone debug mode, not communicating with other agents.
You can directly test this agent's tools and output.

Please analyze data/experiment_1.csv
```

## Agent Prompts

AutoReport uses a progressive loading system for agent prompts:

- **Identity** (loaded at startup): Brief role definition (~100-200 words)
- **Full Instructions** (loaded on first activation): Detailed workflow, reference handling, narrative style, output format

Prompt templates are located in `autoreport/templates/agents/`:
- `main_agent.md` - Main coordination agent
- `data_analysis_agent.md` - Data processing and analysis
- `plotting_agent.md` - Data visualization
- `theory_agent.md` - Theoretical derivation
- `report_agent.md` - LaTeX report writing

## Report Templates

Built-in report templates are in `autoreport/templates/reports/`:

- `default_experiment_report.tex` - Standard physics experiment report template
- `requirements.md` - Narrative style and formatting guidelines
- `README.md` - Template documentation

Users can override built-in templates by placing custom templates in `project/references/`.

**Priority**: User templates > Built-in templates > Standard LaTeX

## MinerU Integration

AutoReport uses [MinerU](https://mineru.net/) CLI for PDF parsing.

### Setup

1. Install and authenticate mineru-open-api:
```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
```
For more details, see the [mineru-open-api documentation](https://mineru.net/ecosystem?tab=cli).

2. Create an account on [MinerU](https://mineru.net/apiManage/token) and obtain an API key. Then authenticate via CLI:
```bash
mineru-open-api auth
```

3. The system will check availability on startup and show a warning if not installed.

### Features

- Converts PDF, images, DOCX, PPTX, XLSX to Markdown
- Extracts text, images, tables, and formulas
- Supports batch processing (up to 200MB, 600 pages per file)
- CLI-based, no local server required

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Reference Projects

- [cc-switch](https://github.com/farion1231/cc-switch) — Provider preset templates (50+ providers), multi-configuration switching, category-based preset selector
- [OpenClaw](../openclaw) — Plugin-based multi-provider system (50+ LLM providers), model catalog management, provider configuration patterns
- [DeepCode](../DeepCode) — API configuration (YAML secrets + env fallback), multi-provider support, error handling, loop detection
- [nanobot](../nanobot) — AgentLoop core architecture, tool definitions, multi-provider native SDK, compact/command system, Pydantic config schema

## License

MIT License - see LICENSE file for details
