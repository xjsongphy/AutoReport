# DeepCode & Nanobot 工具清单

本项目借鉴 DeepCode 和 nanobot 的工具设计，以下为两个项目的完整工具列表，供后续设计 AutoReport 工具集时参考。

---

## DeepCode 工具

### 代码实现工具 (code_implementation_server.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `read_file` | 读取文件内容，支持行范围 | file_path, start_line, end_line |
| `read_multiple_files` | 批量读取多个文件 | file_requests, max_files |
| `write_file` | 写入文件，支持自动创建目录和备份 | file_path, content, create_dirs, create_backup |
| `write_multiple_files` | 批量写入多个文件 | file_implementations, create_dirs, create_backup, max_files |
| `execute_python` | 执行 Python 代码 | code, timeout |
| `execute_bash` | 执行 bash 命令，屏蔽危险命令 | command, timeout |
| `search_code` | 搜索代码文件内容，支持正则 | pattern, file_pattern, use_regex, search_directory |
| `get_file_structure` | 获取目录结构 | directory, max_depth |
| `set_workspace` | 设置工作目录 | workspace_path |
| `get_operation_history` | 获取操作历史 | last_n |
| `read_code_mem` | 读取代码摘要记忆 | file_paths |

### 搜索工具 (bocha_search_server.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `bocha_web_search` | 网页搜索 | query, freshness, count |
| `bocha_ai_search` | 语义搜索 | query, freshness, count |

### 命令执行工具 (command_executor.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `execute_commands` | 批量执行命令，Windows 自动转译 | commands, working_directory |
| `execute_single_command` | 执行单条命令 | command, working_directory |

### 文档分割工具 (document_segmentation_server.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `analyze_and_segment_document` | 分析文档结构并智能分段 | paper_dir, force_refresh |
| `read_document_segments` | 按查询类型读取文档片段 | paper_dir, query_type, keywords, max_segments |
| `get_document_overview` | 获取文档概览 | paper_dir |

### 代码引用索引工具 (code_reference_indexer.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `search_code_references` | 搜索索引中的参考代码 | indexes_path, target_file, keywords, max_results |
| `get_indexes_overview` | 获取索引概览 | indexes_path |

### Git 工具 (git_command.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `download_github_repo` | 从自然语言指令下载 GitHub 仓库 | instruction |
| `parse_github_urls` | 解析 GitHub URL | text |
| `git_clone` | 克隆仓库 | repo_url, target_path, branch |

### PDF 工具 (pdf_downloader.py / pdf_converter.py / pdf_utils.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `download_files` | 下载或移动文件，自动转 Markdown | instruction |
| `parse_download_urls` | 解析 URL 和路径 | text |
| `download_file_to` | 下载指定文件到指定位置 | url, destination, filename |
| `move_file_to` | 复制文件到指定位置（保留原文件） | source, destination, filename |
| `convert_to_pdf` | 文档转 PDF（Office/文本） | file_path, output_dir |
| `convert_office_to_pdf` | Office 文档转 PDF（LibreOffice） | doc_path, output_dir |
| `convert_text_to_pdf` | 文本/Markdown 转 PDF（ReportLab） | text_path, output_dir |
| `check_dependencies` | 检查依赖是否安装 | 无 |
| `read_pdf_metadata` | 读取 PDF 元数据 | file_path |

---

## Nanobot 工具

### 文件系统工具 (filesystem.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `read_file` | 读取文件，支持行范围和 PDF 分页 | path, offset, limit, pages |
| `write_file` | 写入文件 | path, content |
| `edit_file` | 替换文件中的文本 | path, old_text, new_text, replace_all |
| `list_dir` | 列出目录内容 | path, recursive, max_entries |

### 搜索工具 (search.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `glob` | 按模式查找文件 | pattern, path, head_limit, offset, entry_type |
| `grep` | 正则搜索文件内容 | pattern, path, glob, type, output_mode, head_limit, ... |

### Shell 工具 (shell.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `exec` | 执行 shell 命令，带安全限制 | command, working_dir, timeout |

### 消息工具 (message.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `message` | 向用户发送消息 | content, channel, chat_id, message_id, media |

### Web 工具 (web.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `web_search` | 网页搜索 | query, count |
| `web_fetch` | 抓取网页内容 | url, extractMode, maxChars |

### Notebook 工具 (notebook.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `notebook_edit` | 编辑 Jupyter notebook 单元格 | path, cell_index, new_source, cell_type, edit_mode |

### 调度工具 (cron.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `cron` | 定时任务管理 | action, name, message, every_seconds, cron_expr, ... |

### 子 Agent 工具 (spawn.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `spawn` | 生成子 Agent 执行后台任务 | task, label |

### 自身状态工具 (self.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `my` | 查看/设置 Agent 运行时配置 | action, key, value |

### MCP 包装工具 (mcp.py)

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `mcp_{server}_{tool}` | 包装 MCP 服务器工具为原生工具 | 动态（继承 MCP 定义） |
| `mcp_{server}_resource_{name}` | 包装 MCP 资源为只读工具 | 无 |
| `mcp_{server}_prompt_{name}` | 包装 MCP 提示为工具 | 动态（提示参数） |

---

## 对 AutoReport 的启示

### 可以直接借鉴的工具

- **read_file / write_file / edit_file** — 文件操作基础
- **list_dir / glob / grep** — 文件搜索和目录浏览
- **exec** — Shell 命令执行（数据分析、LaTeX 编译）
- **read_file (PDF)** — PDF 读取（nanobot 原生支持）

### 需要新增的工具

- **PDF 解析** — 调用 mineru-open-api 将 PDF 转为 Markdown
- **LaTeX 编译** — 调用 xelatex/lualatex 编译，支持错误捕获
- **数据读取** — 读取 CSV/Excel，返回结构化摘要
- **Python 执行** — 执行数据分析代码（可借鉴 DeepCode 的 execute_python）
- **图片管理** — 图片生成和引用管理

### 工具隔离策略

按 Agent 分配不同工具子集：
- 数据分析 Agent：read_file, write_file(仅 data/processed/), exec(Python), 数据读取
- 图像绘制 Agent：read_file, write_file(仅 code/), exec(Python), 图片管理
- 理论推导 Agent：read_file, write_file(仅 theory/)
- 报告撰写 Agent：read_file, write_file(仅 tex/), edit_file(仅 tex/), LaTeX 编译
- 主 Agent：全部工具 + spawn/消息
