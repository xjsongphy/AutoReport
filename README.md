# AutoReport

[中文](README_zh.md)

A multi-agent collaborative automated physics experiment report writing system. Users provide experimental data and reference materials, then agents collaboratively generate LaTeX reports through theoretical derivation, data analysis, visualization, and typesetting.

## Features

### Core Capabilities
- **Multi-Agent Collaboration** — Main Agent orchestrates, with four sub-agents (Data Analysis, Plotting, Theory, Report) each specializing in their domain
- **Directory Permission Isolation** — Each agent can only write to designated directories, preventing cross-contamination
- **Checkpoint Rollback** — Automatically creates checkpoints at key nodes, can rollback to any historical state
- **Interactive Adjustment** — Users can send messages to any agent at any time for intervention and optimization

### UI/UX (VSCode/Claude Code Style)
- **Streaming Responses** — Real-time agent output display, word-by-word streaming
- **Recent Projects Cache** — VSCode-style recent projects list, cached in `~/.autoreport/recent_projects.json`
- **File Explorer** — VSCode-style resource manager with 22px row height, 16px icons, concise labels (Data, References, Theory, Code, Tex)
- **Context Chip Bar** — Visual indicator for file/line selections with toggle to include/exclude from messages
- **Chat Interface** — Codex-style conversation display with proper markdown rendering

### Developer Tools
- **@ File References** — Type `@` in chat to fuzzy-search and insert file references as markdown links
- **Selected Line Context** — Text selections in preview pane are automatically appended to agent messages
- **Sub-Agent Debug Mode** — Disconnect from Main Agent channel, test individual agents independently
- **Ctrl+C Exit** — Graceful shutdown support

### LLM Integration
- **Multi-Provider Support** — Anthropic, OpenAI, DeepSeek, etc. Runtime model switching
- **Provider Presets** — 50+ provider templates from [cc-switch](https://github.com/farion1231/cc-switch)
- **Progressive Prompt Loading** — Identity at startup, full instructions on first activation (fast startup, rich context)

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

> If `autoreport` command is not found, use `uv run autoreport` instead, or activate the virtual environment first.

First launch prompts for API configuration. You can also pre-configure via environment variables:

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
│   └── processed/   # Data Analysis Agent output only
├── references/      # Reference materials (PDF, images), custom templates
├── theory/          # Theory Agent output only
├── code/            # Plotting Agent code and generated images only
└── tex/             # Report Agent LaTeX source and compiled output only
```

### Agent Permissions

| Agent | Write Directory | Read Scope |
|-------|----------------|------------|
| Main Agent | coordinates only | All directories |
| Data Analysis | `data/processed/` only | All directories |
| Plotting | `code/` only | All directories |
| Theory | `theory/` only | All directories |
| Report | `tex/` only | All directories |
| User | `data/`, `references/` | All directories |

**Tool Isolation**: Each sub-agent receives a restricted tool subset matching their write permissions. Agents cannot modify files outside their designated directory.

## Architecture

```
autoreport/
├── app.py                 # Entry point: CLI parsing, LoopManager startup
├── config/                # Pydantic-based config (YAML loading, API key validation)
├── core/
│   ├── loops/            # Agent runtime: LoopManager, AgentLoop, MessageBus
│   ├── providers/        # LLM provider abstraction (factory, base classes)
│   ├── prompts/          # Progressive prompt loading (identity → full instructions)
│   └── tools/            # Tool system (registry, file tools, exec tools, PDF tool)
├── gui/                  # PyQt6 interface (main window, dialogs, widgets)
│   └── widgets/          # Reusable components (file tree, preview, agent panel)
├── interfaces/           # GUI-backend protocol (Protocol definitions, message types)
├── templates/            # Built-in templates (agent prompts, report templates)
└── utils/                # Logging configuration (loguru)
```

### Key Patterns

**AgentLoop**: Each agent runs its own async loop. Processes messages through LLM chat with tool definitions, then executes tool calls in a max-iteration loop.

**MessageBus**: Async pub/sub system. Main Agent sends coordination messages to sub-agents; sub-agents report issues back. Users can message any agent directly.

**Debug Mode**: Sub-agents disconnect from Main Agent message channel, accept only direct user input. Activated via GUI toggle or `--debug-agent` CLI argument.

**Progressive Prompt Loading**: Agents load a lightweight identity prompt at startup, then load full instructions on first message. Cached afterward.

## Development

### Run Tests

```bash
uv run pytest -v
```

### Code Linting

```bash
uv run ruff check autoreport tests
uv run ruff check --fix autoreport tests
```

### Run Single Test

```bash
uv run pytest tests/test_agent_loop.py -v
```

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
    retry_max_tokens: 16384
    temperature: 0.1
    max_tool_iterations: 200
```

### Provider Configuration

Supports 50+ providers via [cc-switch](https://github.com/farion1231/cc-switch) presets:

```yaml
providers:
  active: "anthropic-default"
  configurations:
    - name: "Anthropic (Official)"
      provider: "anthropic"
      api_key: null       # Set via ANTHROPIC_API_KEY env var
      default_model: "claude-sonnet-4-20250514"
      enabled: true
```

## Debug Mode

Sub-agents support standalone debug mode for isolated testing.

### Usage

**GUI**: Click the "Debug Mode" button in the sub-agent panel.

**CLI**: Start with `--debug-agent`:

```bash
autoreport --debug-agent data_analysis
autoreport --debug-agent data_analysis --debug-agent plotting
```

Valid agents: `data_analysis`, `plotting`, `theory`, `report`

## Agent Prompts

Located in `autoreport/templates/agents/`:

- `main_agent.md` — Dynamic scheduling, quality review checklist
- `data_analysis_agent.md` — Data annotation template, theory comparison
- `plotting_agent.md` — Figure annotation template, self-verification
- `theory_agent.md` — Formula metadata template
- `report_agent.md` — Completeness check, template priority

## MinerU Integration

[MinerU](https://mineru.net/) CLI for PDF parsing.

### Setup

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api auth
```

## Reference Projects

- [cc-switch](https://github.com/farion1231/cc-switch) — Provider presets (50+ providers)
- [DeepCode](../DeepCode) — API config, multi-provider support, error handling
- [nanobot](../nanobot) — AgentLoop architecture, tool definitions
- [codex](../codex) — UI design patterns, streaming implementation

## License

MIT License
