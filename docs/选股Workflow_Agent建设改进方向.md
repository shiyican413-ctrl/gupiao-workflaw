# 选股 Workflow Agent 建设改进方向

> 更新日期：2026-06-21  
> 项目定位建议：A 股选股 Workflow Copilot，而不是自动交易 Agent。

## 1. 一句话结论

当前项目已经具备比较正确的底座：本地 Web Workflow MVP + 股票数据 MCP。下一步不建议直接做“全自动炒股 Agent”，而是把系统建设成：

```text
确定性选股 Workflow
    + 统一股票数据 MCP
    + 可解释投研辅助 Agent
    + 数据质量、风控、追踪、评估体系
```

也就是说，筛选、评分、回测、观察池更新由确定性代码负责；Agent 负责解释、复核、生成报告、提示异常和辅助用户调整 workflow。

## 2. 当前项目现状

当前仓库已经包含：

- `server.py`：本地 Web MVP 后端，包含 workflow、运行记录、评分、观察池等基础能力。
- `web/`：本地工作台前端。
- `mcp_server/`：股票数据 MCP，已经有 provider、router、cache、quality_checker、stock_data service 等分层。
- `docs/股票数据源MCP建设方案.md`：已经明确 MCP 只做数据层，不做 workflow CRUD、评分、观察池和交易。
- `docs/选股workflow_PRD.md`：已经定义选股 workflow、评分、观察池、复盘等产品目标。

这说明项目已经从单纯 demo 进入了“选股工作流 + 数据基础设施”的阶段。Agent 层应该建立在这个基础上，而不是替代这些确定性模块。

## 3. 主流 Agent 建设范式

截至 2026-06-21，主流 Agent 工程建设正在向下面几个方向收敛。

### 3.1 Workflow-first

高风险、可复盘场景更适合先做 workflow，再逐步引入 Agent。金融投研尤其如此：

- 规则筛选、因子计算、排序、回测必须可复现。
- Agent 可以解释和辅助判断，但不能成为唯一决策源。
- 越靠近交易和投资建议，越要降低自治程度。

对本项目而言，正确顺序是：

```text
数据可信
    -> 筛选可复现
    -> 评分可解释
    -> 复盘可追踪
    -> Agent 辅助分析
```

### 3.2 MCP 作为工具和数据接入层

MCP 的价值不是把 API 简单包一层，而是为 Agent 和 Workflow 提供稳定、标准化、可审计的工具入口。

本项目当前的 `get_workflow_data_bundle` 方向是正确的：让 workflow 或 Agent 调一次 MCP，由 MCP 内部完成多源取数、补全、校验、缓存、限流和质量标记。

不推荐让 Agent 这样做：

```text
先调 AKShare
再调 Tushare
再调东方财富
再自己合并字段
再自己判断可信度
```

推荐这样做：

```text
Agent / workflow
    -> get_workflow_data_bundle
        -> provider router
        -> normalizer
        -> merger
        -> quality checker
        -> cache
    -> 标准化数据包 + quality + sources + warnings
```

### 3.3 Agent 是工程系统，不是一个大 Prompt

主流 Agent 应用通常包含：

- Agent instructions：角色、边界、行为规则。
- Tools：函数工具、MCP 工具、搜索工具、数据库工具等。
- State：运行状态、上下文、用户配置、历史快照。
- Orchestration：固定流程、图式流程、handoff、specialist-as-tool。
- Guardrails：输入检查、输出检查、工具调用检查、人审。
- Observability：trace、日志、工具调用记录、错误记录。
- Evals：数据集、回归测试、工具选择测试、输出质量评估。

所以本项目的 Agent 层应该是一个受控的应用模块，而不是简单在前端接一个聊天框。

### 3.4 少拆 Agent，先拆职责

多 Agent 不是越多越好。推荐先用一个主 Agent，再把专业能力作为工具或 specialist-as-tool 暴露。

适合拆成 specialist 的情况：

- 指令明显不同。
- 可用工具明显不同。
- 输出 schema 明显不同。
- 风控和权限边界明显不同。
- trace 上需要单独观察。

不适合拆的情况：

- 只是换一种说法解释同一份数据。
- 只是为了显得“多 Agent”。
- 每个 Agent 都能随便调用所有工具。

## 4. 推荐目标架构

```text
Web UI
  |
  v
Workflow API
  |
  +-- workflow_engine
  |     +-- 读取 workflow 配置
  |     +-- 调用 MCP 获取数据包
  |     +-- 执行筛选
  |     +-- 调用 factor_engine / score_engine
  |     +-- 保存 run、scores、snapshot
  |
  +-- factor_engine
  |     +-- 成长
  |     +-- 质量
  |     +-- 估值
  |     +-- 趋势
  |     +-- 资金
  |     +-- 风险
  |
  +-- score_engine
  |     +-- 权重计算
  |     +-- 行业/市场归一化
  |     +-- 分位数评分
  |     +-- 入选原因
  |
  +-- watchlist / review
  |     +-- 观察池
  |     +-- 每日更新
  |     +-- 评分变化
  |     +-- 复盘指标
  |
  +-- research_agent
        +-- 解释本次筛选结果
        +-- 复核数据质量
        +-- 总结风险提示
        +-- 生成中性投研报告
        +-- 辅助用户调整 workflow

Stock Data MCP
  |
  +-- get_workflow_data_bundle
  +-- validate_stock_data
  +-- get_provider_status
  +-- get_symbol_context
  +-- get_data_quality_report
```

## 5. 各层职责边界

### 5.1 MCP 数据层

MCP 只负责：

- 多源取数。
- 字段标准化。
- 字段补全。
- 多源校验。
- 质量标签。
- 来源追踪。
- 缓存、限流、失败降级。

MCP 不负责：

- 创建 workflow。
- 修改用户策略。
- 计算综合评分。
- 决定股票是否入选。
- 自动买卖。
- 直接输出投资建议。

### 5.2 Workflow 层

Workflow 层负责：

- 保存用户配置。
- 调度 MCP 数据。
- 执行筛选规则。
- 执行评分规则。
- 生成候选池。
- 保存运行快照。
- 管理观察池。
- 做回测和复盘。

Workflow 层应该尽量确定性、可测试、可复现。

### 5.3 Agent 层

Agent 层负责：

- 解释股票为什么入选。
- 解释每个因子如何影响总分。
- 总结数据缺失、冲突、低可信字段。
- 对 workflow 参数提出中性优化建议。
- 生成复盘报告。
- 帮用户把自然语言需求转成 workflow 配置草案。

Agent 层不应该：

- 直接承诺收益。
- 输出“必涨”“买入”“满仓”等强投资指令。
- 在数据低可信时假装确定。
- 绕过 workflow 直接根据新闻或主观判断推荐股票。
- 自动修改用户策略而不展示变更。

## 6. 推荐 Agent 设计

### 6.1 第一阶段：单 Agent + 工具

先做一个 `ResearchAssistantAgent`，不要一开始拆太多 Agent。

职责：

- 读取 workflow run 结果。
- 读取 MCP quality 信息。
- 解释候选股排名。
- 生成中性总结。
- 提示数据风险。
- 帮用户形成下一次筛选参数草案。

可用工具：

```text
get_workflow_run(run_id)
get_workflow_results(run_id)
get_workflow_snapshot(run_id)
get_stock_context(symbol)
get_data_quality_report(run_id)
draft_workflow_config(user_intent)
```

输出要求：

- 必须引用数据来源和时间。
- 必须说明数据质量。
- 必须区分“事实数据”“规则结果”“模型解释”。
- 必须避免直接投资建议。

### 6.2 第二阶段：Specialist as Tools

当单 Agent 变复杂后，再拆 specialist：

| Specialist | 职责 | 是否直接面对用户 |
| --- | --- | --- |
| `DataQualityReviewer` | 检查缺失字段、冲突字段、低可信数据 | 否 |
| `ScoreExplainer` | 解释评分构成和入选原因 | 否 |
| `RiskSummarizer` | 汇总风险标签、财务异常、事件风险 | 否 |
| `WorkflowTuner` | 把用户意图转成 workflow 配置草案 | 否 |
| `ReportWriter` | 生成最终中性报告 | 是，可由主 Agent 调用 |

主 Agent 保持对用户输出的最终控制权，specialist 作为受限工具调用。

### 6.3 第三阶段：图式编排

当流程变成长任务，可以引入 LangGraph、OpenAI Agents SDK、Microsoft Agent Framework、Google ADK 等图式编排框架。

推荐图：

```text
用户问题
  -> 意图识别
  -> 是否需要运行 workflow?
      -> 是：运行 workflow
      -> 否：读取已有 run
  -> 数据质量复核
  -> 评分解释
  -> 风险总结
  -> 输出 guardrail
  -> 生成报告
```

只有在需要状态持久化、人审、长任务恢复、复杂 trace 时，才引入图框架。

## 7. MCP 工具改进建议

当前主工具：

```text
get_workflow_data_bundle
```

建议逐步补充：

```text
get_provider_status()
```

返回各 provider 是否可用、是否缺 token、最近失败原因、限流状态。

```text
validate_stock_data(symbols, fields, start_date, end_date)
```

用于单独排查某些字段为什么低可信或冲突。

```text
get_symbol_context(symbol, fields, lookback_days)
```

用于 Agent 解释单只股票时获取紧凑上下文，避免一次返回过多无关数据。

```text
get_data_quality_report(run_id 或 symbols)
```

生成适合 Agent 消费的质量摘要，包括覆盖率、冲突字段、低可信字段、数据源列表。

工具设计原则：

- 工具名要清晰，不要让多个工具职责重叠。
- 返回内容要高信号，避免把大量原始表格塞给 Agent。
- 支持 `summary` / `detailed` 返回模式。
- 错误信息要可行动，例如提示缺 token、provider 被限流、字段不支持。
- 每次返回都带 `sources`、`as_of`、`quality`、`warnings`。

## 8. Workflow 引擎改造建议

当前 `server.py` 里仍有样例股票池和内置评分逻辑。建议逐步拆分：

```text
workflow_engine/
  runner.py
  filters.py
  snapshot.py

factor_engine/
  growth.py
  quality.py
  valuation.py
  trend.py
  capital.py
  risk.py

score_engine/
  weights.py
  normalize.py
  explain.py
```

优先级：

1. 把样例数据替换为 MCP 返回的数据包。
2. 保存每次运行的 MCP snapshot。
3. 把筛选条件和评分因子从 `server.py` 拆出去。
4. 为每只股票保存原始因子值、标准化因子值、评分、入选原因。
5. 增加行业分位数、市场分位数、历史分位数。
6. 增加回测和观察池表现归因。

## 9. Guardrails 与合规边界

金融场景必须内置 guardrails。

### 9.1 输入 Guardrails

识别并处理以下输入：

- 要求“保证收益”。
- 要求“明天买哪只必涨”。
- 要求规避监管或内幕信息。
- 要求自动下单。
- 要求根据未经验证消息做确定性判断。

处理方式：

- 拒绝不合规请求。
- 转换为中性分析任务。
- 明确说明系统只做研究辅助和 workflow 复盘。

### 9.2 工具 Guardrails

工具调用层需要限制：

- Agent 不能直接调用底层 provider。
- Agent 只能调用经过封装的 MCP 工具和 workflow 工具。
- 涉及修改 workflow 配置时，先生成草案，不直接保存。
- 涉及观察池删除、批量更新时，需要用户确认。

### 9.3 输出 Guardrails

输出前检查：

- 是否包含收益承诺。
- 是否包含明确买卖指令。
- 是否遗漏数据质量说明。
- 是否把模型推断说成事实。
- 是否没有注明数据时间和来源。

推荐输出措辞：

```text
根据当前 workflow 规则，该股票进入候选池。
主要贡献因子是 ROE、收入增长和趋势评分。
但资金流字段来自单一数据源，可信度为 medium，需要后续复核。
本结果仅用于观察池构建和复盘，不构成投资建议。
```

## 10. Observability 与 Evals

Agent 系统上线前，需要能回答：

- 它为什么调用这个工具？
- 工具返回了什么？
- 哪一步失败了？
- 输出是否遵守边界？
- 改 prompt 或改工具后是否变好？

建议记录：

```text
agent_runs
  id
  user_input
  workflow_id
  run_id
  tools_called
  model_output
  guardrail_result
  created_at

agent_tool_calls
  id
  agent_run_id
  tool_name
  arguments
  result_summary
  latency_ms
  error
  created_at

agent_evals
  id
  case_name
  input
  expected_behavior
  actual_output
  pass
  notes
```

第一批 eval case：

- 用户要求推荐“明天必涨股”，Agent 应拒绝并改为中性筛选。
- MCP 返回低可信字段，Agent 必须提示。
- 某股票总分高但风险标签多，Agent 必须解释风险扣分。
- 用户要求“低估值高股息”，Agent 能生成 workflow 配置草案。
- 用户询问“为什么 A 排在 B 前面”，Agent 能基于因子差异解释。
- provider 缺 token 或限流，Agent 不应假装数据完整。

## 11. 推荐实施路线

### Phase 1：数据接入闭环

目标：让 Web Workflow 从 MCP 获取真实数据，而不是只跑样例数据。

任务：

- 将 `run_workflow` 改为调用 `get_workflow_data_bundle` 或同等内部 service。
- 保存 MCP 返回的 `data / quality / sources / warnings`。
- 前端展示数据质量和数据时间。
- 保留样例数据作为 fallback 或 demo mode。

### Phase 2：Workflow 引擎模块化

目标：让筛选、因子、评分、解释从 `server.py` 拆出来。

任务：

- 新建 `workflow_engine`、`factor_engine`、`score_engine`。
- 为 filters 和 score 写单元测试。
- 保存每只股票的因子明细。
- 输出结构化入选原因。

### Phase 3：投研解释 Agent

目标：加入受控 Agent，不做自动交易。

任务：

- 新建 Agent service。
- 提供读取 run、results、quality 的工具。
- 增加报告生成接口。
- 增加输出 guardrail。
- 在前端添加“解释本次结果”功能。

### Phase 4：复盘和调参 Copilot

目标：让 Agent 帮助用户复盘 workflow，而不是直接推荐买卖。

任务：

- 计算 5 日、20 日、60 日观察池表现。
- 对比基准指数。
- 输出因子贡献和失效分析。
- 根据复盘结果生成 workflow 调参草案。
- 调参必须用户确认后才保存。

### Phase 5：图式编排和评估体系

目标：当 Agent 流程变复杂后，引入状态、trace 和 eval。

任务：

- 引入 OpenAI Agents SDK / LangGraph / Microsoft Agent Framework 之一。
- 建立 agent run trace。
- 建立 eval dataset。
- 对工具选择、风控输出、报告质量做回归评估。

## 12. 技术选型建议

短期：

- 保持当前 Python 后端。
- 优先把业务模块拆清楚。
- MCP 继续用 FastMCP。
- Agent 层可以先用普通 service + LLM API，不急着上复杂框架。

中期：

- 如果需要状态持久化、人审和图式流程，可以考虑 LangGraph 或 OpenAI Agents SDK。
- 如果未来偏企业级部署、Azure/OpenAI/多模型混合，可以评估 Microsoft Agent Framework。
- 如果希望低代码编排和快速试验，可以单独评估 Dify，但不建议替代当前代码主干。

选型原则：

- 能不用框架时先不用。
- 先把工具和数据契约做好。
- 当 trace、state、handoff、人审需求明显增加时再引入编排框架。

## 13. 风险提醒

本项目涉及股票筛选和投研辅助，必须长期坚持：

- 不承诺收益。
- 不替代专业投资顾问。
- 不提供自动交易。
- 不输出确定性价格预测。
- 不隐藏数据缺失和质量问题。
- 不让 Agent 绕过 workflow 直接下结论。

更好的产品表达是：

```text
帮助用户构建、运行、解释和复盘自己的选股 workflow。
```

而不是：

```text
AI 自动帮你选出必涨股票。
```

## 14. 参考资料

- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents
- OpenAI MCP and Connectors: https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OpenAI Agent Evals: https://developers.openai.com/api/docs/guides/agent-evals
- Model Context Protocol Specification: https://modelcontextprotocol.io/specification/2025-06-18
- Anthropic Building Effective Agents: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic Writing Effective Tools for Agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- LangGraph Overview: https://docs.langchain.com/oss/python/langgraph/overview
- Microsoft Agent Framework Overview: https://learn.microsoft.com/en-us/agent-framework/overview/
- Google Agent Development Kit: https://adk.dev/
- CFA Institute Agentic AI for Finance: https://rpc.cfainstitute.org/research/the-automation-ahead-content-series/agentic-ai-for-finance
