# A股选股 Workflow MVP

一个本地可运行的 A 股选股工作台 MVP，并配套一个面向 workflow 的股票数据 MCP。

## 项目结构

```text
.
├─ mcp_server/              # 股票数据 MCP：多源取数、补全、校验、质量标记
│  ├─ providers/            # AKShare / Tushare / Baostock / efinance / HTTP 数据源适配
│  ├─ services/             # 路由、缓存、质量校验、workflow 数据包服务
│  ├─ server.py             # FastMCP 工具注册
│  └─ __main__.py           # python -m mcp_server 入口
├─ web/                     # 本地 Workflow MVP 前端静态资源
├─ tests/                   # 自动化测试预留
├─ scripts/                 # 手动诊断脚本
├─ docs/                    # PRD、数据源调研、MCP 方案文档
├─ data/                    # 本地 SQLite 数据库，运行时生成/维护
├─ server.py                # 本地 Web MVP 后端入口
├─ pyproject.toml           # Python 包和依赖配置
└─ .mcp.json                # MCP 客户端启动配置
```

## 启动 Web MVP

```bash
python server.py
```

默认访问：

```text
http://127.0.0.1:8765
```

指定端口：

```bash
python server.py 9000
```

## 启动 MCP

MCP 客户端会读取 `.mcp.json`，使用：

```bash
python -m mcp_server
```

当前 MCP 主工具：

```text
get_workflow_data_bundle
```

它会在内部自动多源取数、字段补全、交叉校验，并返回：

```text
data
coverage
quality
sources
warnings / errors
```

## 文档

- `docs/选股workflow_PRD.md`
- `docs/API数据源质量文档.md`
- `docs/股票数据源MCP建设方案.md`

## 运行数据

本地运行数据放在 `data/`：

- `data/stock_workflow.db`：Web MVP 的 workflow/观察池/运行记录。
- `data/mcp_workflow.db`：历史遗留或 MCP 相关本地库。
- `data/stock_data.db`：MCP 数据服务预留库。

这些文件是本地运行状态，不建议提交到 Git。

