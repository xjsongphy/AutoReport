# AutoReport

基于Agent的自动化物理实验报告撰写系统。

## 功能特性

- 多Agent协作（主Agent、数据分析、图像绘制、理论推导、报告撰写）
- 支持多种LLM Provider（Anthropic、OpenAI、DeepSeek）
- LaTeX报告自动生成
- 检查点回滚功能
- 子Agent调试模式

## 安装

```bash
uv sync
```

## 运行

```bash
autoreport
```

## 配置

启动时会提示配置API密钥，或通过环境变量配置：
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
