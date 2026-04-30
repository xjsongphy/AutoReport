# 报告模板

此目录包含 AutoReport 的内置报告模板。

## 模板文件

### template.tex（推荐）⭐

**北京大学物理学院近代物理实验报告官方模板**

- **文档类**: PKUMpLtX（基于 revtex4-2）
- **适用场景**: 北京大学近代物理实验课程
- **特点**:
  - 符合 AIP 期刊和《物理学报》格式要求
  - 完整的报告结构（引言、理论、实验装置、结果及讨论、结论）
  - 详细的注释说明和示例
  - 内置近代物理实验报告写作要求
  - 支持中文（自动处理标点、格式）
  - 专业的图表和参考文献处理

**章节结构**:
1. 标题页（含摘要、关键词）
2. 引言
3. 理论（可选）
4. 实验装置
5. 结果及讨论（主体部分）
6. 结论
7. 致谢
8. 参考文献
9. 附录（思考题）

**使用方法**:
```latex
\documentclass[font=default]{mpltx}
...
\begin{document}
...
\end{document}
```

**编译**:
```bash
xelatex -interaction=nonstopmode template.tex
xelatex -interaction=nonstopmode template.tex
```

### default_experiment_report.tex（通用模板）

标准物理实验报告模板：
- **文档类**: article
- **适用场景**: 通用物理实验报告
- **特点**:
  - 更通用的结构
  - 适用于非北大课程
  - 易于定制

## requirements.md

详细的报告写作规范与指南，整合了：

1. **官方要求**: 北京大学近代物理实验课程写作规范
2. **叙述风格**: AutoReport 补充的叙述风格指南
3. **图表规范**: 基于顶级期刊（Nature、Science、Cell）的要求
4. **格式标准**: LaTeX 编译、引用、交叉引用等

## 使用方法

### 内置模板（本目录）

自动使用，当 `project/references/` 中没有自定义模板时。

### 用户模板（更高优先级）

放置在 `project/references/` 目录：

```
project/
├── references/
│   ├── template.tex          # 用户自定义模板（最高优先级）
│   ├── custom_template.tex
│   └── requirements.md       # 用户自定义要求
├── data/
├── theory/
├── code/
└── tex/
```

## 模板优先级

1. **用户模板** - `project/references/template.tex`
2. **北大官方模板** - `autoreport/templates/reports/template.tex` ⭐
3. **通用模板** - `autoreport/templates/reports/default_experiment_report.tex`
4. **标准模板** - LaTeX article 类

## PKUMpLtX 模板特点

### 文档类选项

```latex
\documentclass[font=default]{mpltx}
```

- `font=default`: 使用默认字体
- `font=song`: 使用宋体
- `font=kai`: 使用楷体
- `font=fang`: 使用仿宋
- `quanjiao`: 使用全角标点和实心点句号

### 专用命令

- `\title{}` - 实验题目
- `\author{}` - 姓名
- `\emailphone{email}{phone}` - 邮箱和电话
- `\affiliation{}` - 所属单位
- `\date{\zhdate{2020/12/1}}` - 中文日期
- `\date{\localedate{2020}{12}{1}}` - 本地化日期

### 参考文献处理

使用 BibTeX：
```latex
\bibliography{bibli}
```

需要对应的 `bibli.bib` 文件。

### 交叉引用

自动带类型引用：
```latex
\autoref{sec:theory}      -> "理论" (第1节)
\autoref{fig:instruments} -> "图1"
\autoref{eq:1}            -> "(1)"
\autoref{tab:table_eg}    -> "表1"
```

## 自定义模板

### 复制官方模板

如果需要自定义，建议基于官方模板修改：

1. 将 `template.tex` 复制到 `project/references/`
2. 根据需要修改章节结构
3. 保持文档类为 `mpltx` 以利用其专业功能

### 创建新模板

如果要创建完全不同的模板：

1. 支持标准 LaTeX 文档类（article, report 等）
2. 包含必要的宏包（ctex, amsmath, graphicx 等）
3. 遵循叙述风格指南（见 requirements.md）
4. 提供清晰的章节结构

## 添加新模板

要添加新的内置模板：

1. 在此目录创建 `.tex` 文件
2. 更新本文档
3. 遵循一致的结构和命名约定

## 编译注意事项

### 必须编译两次

交叉引用需要两次编译才能正确解析：

```bash
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
```

### 常见编译错误

**未定义的引用**:
- 原因：只编译了一次
- 解决：再编译一次

**字体未找到**:
- 原因：指定的字体未安装
- 解决：使用 `font=default` 选项

**中文显示问题**:
- 原因：未使用 xeLaTeX 编译
- 解决：确保使用 `xelatex` 命令

## 图表规范（顶级期刊标准）

详见 [requirements.md](requirements.md) 中的完整规范。

**关键要求**:
- 分辨率：300-1200 DPI
- 格式：PNG/EPS/TIFF
- 配色：色盲友好
- 字体：Arial/Helvetica，8-12pt

## 参考资料

- **PKUMpLtX**: https://github.com/CastleStar14654/PKUMpLtX
- **AIP Style Manual**: 第4版
- **APS Author Guidelines**: https://journals.aps.org/authors
- **Nature Figure Guidelines**: https://sci-draw.com/blog/nature-science-figure-requirements

## 支持

如有问题或建议，请：
1. 查阅 [requirements.md](requirements.md)
2. 参考 template.tex 中的详细注释
3. 查阅 PKUMpLtX 文档
