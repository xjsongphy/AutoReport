# AutoReport

[中文README](README.zh.md)

An automated physics experiment report writing system based on multi-agent collaboration. Users provide experimental data and reference materials, then agents collaboratively generate LaTeX reports through theoretical derivation, data analysis, visualization, and typesetting.

## Features

- **Multi-Agent Collaboration** — Main Agent orchestrates, with four sub-agents (data analysis, plotting, theory, report) each specializing in their domain
- **Multi-Provider Support** — Anthropic, OpenAI, DeepSeek, etc. Runtime model switching, provider switch requires restart
- **Directory Permission Isolation** — Each agent can only write to designated directories, preventing cross-contamination
- **Checkpoint Rollback** — Automatically creates checkpoints at key nodes, can rollback to any historical state
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
uv sync
```

### Running

```bash
autoreport
```

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
    max_tokens: 8192
    temperature: 0.1
    max_tool_iterations: 200
    prompt_templates_dir: "templates/agents"
```

### MinerU API Configuration

```yaml
mineru_api:
  url: "http://localhost:9999"
  enabled: true
  timeout: 300
  validate_on_startup: true  # Soft warning if unavailable
```

### Provider Configuration

```yaml
providers:
  anthropic:
    api_key: null  # Set via ANTHROPIC_API_KEY env var
    api_base: null
  openai:
    api_key: null  # Set via OPENAI_API_KEY env var
    api_base: null
  deepseek:
    api_key: null  # Set via DEEPSEEK_API_KEY env var
    api_base: "https://api.deepseek.com/v1"
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

## MinerU Open API Integration

AutoReport uses [mineru-open-api](https://github.com/opendatalab/MinerU) for PDF parsing.

### Setup

1. Install and start mineru-open-api service:
```bash
pip install mineru-open-api
mineru-open-api --port 9999
```

2. Configure in `autoreport.config.yaml`:
```yaml
mineru_api:
  url: "http://localhost:9999"
  enabled: true
  timeout: 300
```

3. The system will show a soft warning on startup if the API is unavailable, but will still allow the application to run.

### Features

- Converts PDF reference materials to Markdown
- Extracts text, images, and tables
- Supports multi-page documents
- Asynchronous processing with 5-minute timeout

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Reference Projects

- [DeepCode](../DeepCode) — API configuration (YAML secrets + env fallback), multi-provider support, error handling, loop detection
- [nanobot](../nanobot) — AgentLoop core architecture, tool definitions, multi-provider native SDK, compact/command system, Pydantic config schema

## License

MIT License - see LICENSE file for details
