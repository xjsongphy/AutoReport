# MinerU OpenAPI 集成指南

本文档说明如何配置和使用 MinerU OpenAPI 进行 PDF 解析。

## 什么是 MinerU OpenAPI？

MinerU 是一个文档解析工具，支持 PDF、图片、DOCX、PPTX、XLSX 等多种格式的解析。AutoReport 使用 MinerU OpenAPI 将 PDF 参考资料转换为 Markdown 格式，便于 Agent 阅读和处理。

**官方链接:**
- GitHub: https://github.com/opendatalab/MinerU
- API 文档: https://mineru.net/apiManage/docs

## 安装 MinerU OpenAPI

### 方法 1：使用 pip 安装

```bash
pip install mineru-open-api
```

### 方法 2：从源码安装

```bash
git clone https://github.com/opendatalab/MinerU.git
cd MinerU
pip install -e .
```

## 启动服务

### 默认启动（端口 9999）

```bash
mineru-open-api
```

### 自定义端口

```bash
mineru-open-api --port 8080
```

### 指定主机

```bash
mineru-open-api --host 0.0.0.0 --port 9999
```

服务启动后，API 端点为：`http://localhost:9999`

## 配置 AutoReport

### 配置文件设置

编辑 `autoreport.config.yaml`：

```yaml
mineru_api:
  url: "http://localhost:9999"
  enabled: true
  timeout: 300  # 秒
  validate_on_startup: true  # 启动时验证（软警告）
```

### 环境变量设置

也可以通过环境变量配置：

```bash
export MINERU_API_URL="http://localhost:9999"
export MINERU_API_ENABLED="true"
export MINERU_API_TIMEOUT="300"
```

## 验证安装

### 检查服务是否运行

```bash
curl http://localhost:9999
```

如果服务正常运行，应该返回 API 信息。

### 使用 Python 测试

```python
import httpx

async def test_mineru():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:9999")
        print(response.status_code)
        print(response.json())

import asyncio
asyncio.run(test_mineru())
```

## 使用方法

### 通过主 Agent 使用

1. 将 PDF 文件放入项目的 `references/` 目录
2. 向主 Agent 发送消息："请解析 references/handout.pdf"
3. 主 Agent 会调用 parse_pdf 工具解析 PDF
4. 解析结果会保存为 Markdown 文件

### 工具参数

```python
await parse_pdf(
    pdf_path="references/handout.pdf",      # PDF 文件路径（相对于工作区）
    output_path="references/handout.md"     # 可选：输出 Markdown 文件路径
)
```

### 返回结果

```python
{
    "markdown_content": "解析得到的 Markdown 文本",
    "page_count": 10,                       # 页数
    "output_path": "references/handout.md", # 保存路径
    "pdf_path": "/path/to/pdf"             # 原始 PDF 路径
}
```

## 支持的格式

- **PDF**: `.pdf`
- **图片**: `.png`, `.jpg`, `.jpeg`
- **文档**: `.docx`, `.pptx`, `.xlsx`

## 故障排除

### 问题：连接被拒绝

**错误信息**: `Connection refused - service may not be running`

**解决方案**:
1. 检查 MinerU OpenAPI 是否正在运行：
   ```bash
   ps aux | grep mineru
   ```
2. 启动服务：
   ```bash
   mineru-open-api
   ```

### 问题：连接超时

**错误信息**: `Connection timeout - service may be overloaded`

**解决方案**:
1. 增加超时时间：
   ```yaml
   mineru_api:
     timeout: 600  # 增加到 10 分钟
   ```
2. 检查文件大小，大文件需要更长时间处理

### 问题：解析失败

**错误信息**: `Failed to parse PDF: HTTP 500`

**解决方案**:
1. 检查 PDF 文件是否损坏
2. 尝试重新生成 PDF
3. 检查 MinerU 日志查看详细错误信息

## 性能优化

### 处理大文件

对于大 PDF 文件：

1. **增加超时时间**:
   ```yaml
   mineru_api:
     timeout: 600
   ```

2. **使用异步处理**: MinerU OpenAPI 支持异步任务处理

3. **分批处理**: 将大文件分成多个小文件

### 缓存解析结果

解析后的 Markdown 会保存到磁盘，下次直接读取，无需重新解析。

## 软警告模式

AutoReport 使用软警告模式：
- 启动时检查 MinerU OpenAPI 是否可用
- 如果不可用，显示警告但允许应用继续运行
- 只有在真正需要解析 PDF 时才会报错

这样设计的好处：
- 不强制用户必须安装 MinerU OpenAPI
- 可以在没有 PDF 解析需求的情况下正常使用
- 提前提示用户配置问题

## 高级配置

### 使用远程服务

如果 MinerU OpenAPI 部署在远程服务器：

```yaml
mineru_api:
  url: "http://remote-server.example.com:9999"
  enabled: true
  timeout: 300
```

### 使用 Docker 部署

```bash
# 拉取镜像
docker pull opendatalab/mineru-api:latest

# 运行容器
docker run -d -p 9999:9999 opendatalab/mineru-api:latest

# 配置 AutoReport
mineru_api:
  url: "http://localhost:9999"
```

### 使用反向代理

通过 Nginx 配置反向代理：

```nginx
location /mineru/ {
    proxy_pass http://localhost:9999/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

配置 AutoReport：
```yaml
mineru_api:
  url: "https://your-domain.com/mineru"
```

## 参考资料

- [MinerU 官方文档](https://github.com/opendatalab/MinerU)
- [MinerU API 文档](https://mineru.net/apiManage/docs)
- [安装教程](https://github.com/opendatalab/MinerU/blob/master/docs/zh/installation.md)
