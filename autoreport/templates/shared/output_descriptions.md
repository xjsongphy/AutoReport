# Agent Output Descriptions

This file describes each agent's output format, directory, and file naming conventions.
All agents should read these descriptions to understand what to expect from other agents.

## Theory Agent → `theory/`

- `theory.md` — Main derivations with step-by-step explanations and physical intuition
- `formulas.md` — Key formulas table:

| Column | Description |
|--------|-------------|
| 公式 | LaTeX-formatted equation |
| 物理意义 | What physical law or relationship this describes |
| 适用条件 | Key assumptions or domain limits |
| 供谁使用 | Which agent(s) need this: Data Analysis, Plotting, or both |

- `assumptions.md` — List of assumptions and approximations made during derivation

## Data Analysis Agent → `data/processed/`

- `README.md` — Data annotation table:

| Column | Description |
|--------|-------------|
| 文件 | Output data filename |
| 数据来源 | Which raw data file was used |
| 物理量 | What physical quantity this measures |
| 单位 | Measurement units |
| 不确定度 | Uncertainty with type (random/systematic) |
| 理论依据 | Which formula from `theory/formulas.md` was applied |
| 实验值 vs 理论值 | Numerical comparison with deviation |
| 关联实验目的 | How this data supports the experiment's goal |

- `analysis.md` — Methods used, formulas applied, assumptions
- Processed data files (CSV) — Numerical results with units in headers

## Plotting Agent → `code/`

- `README.md` — Figure annotation table:

| Column | Description |
|--------|-------------|
| 图片 | Figure file path (relative to `code/`) |
| 展示内容 | What the figure shows (data type, plot type, axes) |
| 数据来源 | Which processed data file was used |
| 理论叠加 | Which formula or prediction is overlaid |
| 吻合情况 | Whether theory-data agreement is clear |
| DPI | Resolution used |

- `plots/` — Generated PNG images (300+ DPI)
- `scripts/` — Python scripts that generated plots (for reproducibility)

## Report Agent → `tex/`

- `main.tex` — Main LaTeX document (based on selected template)
- `main.pdf` — Compiled output
- `figures/` — Symlink or copy of plots from `code/plots/`
- `sections/` — Individual section files (if template supports `\input{}`)

## Raw Data → `data/` (user input)

- CSV, Excel, or text files with experimental measurements
- Users add files here; Data Analysis Agent reads from here

## Reference Materials → `references/` (user input)

- PDFs, images, custom LaTeX templates
- Higher priority than built-in templates for Report Agent
