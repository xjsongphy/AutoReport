# Report Templates

This directory contains built-in report templates for AutoReport.

## Templates

### `default_experiment_report.tex`

Default physics experiment report template with standard sections:
- Title page
- Introduction
- Theory
- Experimental Setup
- Data Analysis
- Results
- Discussion
- Conclusion
- References

### `requirements.md`

Default reporting requirements and guidelines:
- Narrative style guidelines
- LaTeX formatting standards
- Figure and table conventions
- Citation format

## Usage

**Built-in templates** (this directory):
- Automatically used when no custom templates are provided
- Located in `autoreport/templates/reports/`

**User templates** (higher priority):
- Place in `project/references/` directory
- Filename should be `template.tex` or `custom_template.tex`
- User templates override built-in templates

## Template Priority

1. User templates in `project/references/`
2. Built-in templates in `autoreport/templates/reports/`
3. Standard LaTeX article class

## Customization

Users can customize reports by:
1. Copying built-in template to `project/references/`
2. Modifying the copied template
3. The Report Agent will use the customized version

## Adding New Templates

To add a new built-in template:
1. Create `.tex` file in this directory
2. Update documentation in `README.md`
3. Follow the standard structure for consistency

## LaTeX Compilation

All templates use `xelatex` for compilation:
```bash
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
```

Must compile twice for cross-references to resolve.
