# 股票数据源 MCP 建设方案

> 面向“选股 Workflow”的 best-effort 数据适配层。目标是让 workflow 在当前可用免费/注册数据源能力范围内，拿到尽可能准确、尽可能完整、并且带质量标记的数据。

## 1. 核心定位

这个 MCP 不是单纯把 AKShare、Tushare、腾讯、新浪等 API 包一层，也不是让 Agent 自己选择数据源。

它的定位是：

```text
选股 Workflow 的统一数据入口
    -> MCP 内部多源取数
    -> MCP 内部字段补全
    -> MCP 内部交叉校验
    -> MCP 返回标准化数据、可信度、缺失字段、冲突字段、来源追踪
```

workflow 或 Agent 只调用 MCP。它不需要知道底层到底用了几个 API，也不需要分别调用“一期、二期”。所有数据源调度、兜底和校验都由 MCP 内部完成。

## 2. 建设目标

### 2.1 要做到什么

- 为选股 Workflow 提供统一、稳定的数据接口。
- 在力所能及范围内提供更准确的数据：关键字段尽量多源验证。
- 在力所能及范围内提供更全面的信息：一个源缺字段时，自动从其他源补齐。
- 所有返回数据必须带来源、时间戳和可信度。
- 对缺失字段、冲突字段、低可信字段透明标记，不假装数据完整。
- 支持 workflow 批量取数，避免 Agent 对单只股票反复调用多个工具。
- 支持缓存、限流、失败兜底，降低免费接口的不稳定影响。

### 2.2 不做什么

- 不在 MCP 里做 workflow CRUD。
- 不在 MCP 里做多因子评分。
- 不在 MCP 里做观察池和复盘。
- 不在 MCP 里做自动交易。
- 不承诺免费数据达到交易级实时性。
- 不让大模型直接根据 MCP 输出给出买卖建议。

MCP 只负责数据层。筛选、评分、入选原因、风险提示仍然放在：

```text
workflow_engine
factor_engine
score_engine
watchlist
backtest
```

## 3. 一步到位的使用方式

workflow 后续优先调用一个批量工具：

```text
get_workflow_data_bundle
```

调用示例：

```json
{
  "symbols": ["sh600519", "sz000858", "sz300750"],
  "fields": [
    "quote",
    "kline_daily",
    "valuation",
    "financial",
    "money_flow",
    "sector"
  ],
  "start_date": "2023-01-01",
  "end_date": "2026-06-21",
  "adjust": "qfq",
  "quality_policy": "best_effort"
}
```

MCP 内部会自动完成：

```text
识别需要哪些字段
    -> 选择可用数据源
    -> 并发/批量取数
    -> 字段标准化
    -> 多源补全
    -> 多源校验
    -> 生成质量标签
    -> 返回 workflow 可直接消费的数据包
```

也就是说，Agent 或 workflow 不是这样用：

```text
先调 AKShare
再调 Tushare
再调 Baostock
再自己对比
```

而是这样用：

```text
workflow 调一次 MCP
MCP 内部自己调多个源
MCP 返回合并后的结果
```

## 4. 总体架构

```text
选股 Workflow / AI 辅助层
        |
        v
Stock Workflow Data MCP
        |
        +-- MCP Tools
        |     +-- get_workflow_data_bundle
        |     +-- get_realtime_quote
        |     +-- get_kline
        |     +-- get_financial_indicators
        |     +-- get_valuation
        |     +-- get_money_flow
        |     +-- validate_stock_data
        |
        +-- MCP Resources
        |     +-- stock://providers
        |     +-- stock://schema/quote
        |     +-- stock://schema/kline
        |     +-- stock://schema/financial
        |     +-- stock://quality/latest
        |
        v
数据服务层
        |
        +-- Field Planner        判断 workflow 需要哪些字段
        +-- Provider Router      数据源选择和降级
        +-- Normalizer           字段、单位、日期、代码标准化
        +-- Merger               多源字段补全
        +-- Quality Checker      多源校验与可信度计算
        +-- Cache Manager        缓存
        +-- Rate Limiter         限流
        +-- Error Handler        熔断、重试、失败兜底
        |
        v
Provider 适配器层
        |
        +-- AKShare
        +-- Tushare
        +-- Baostock
        +-- efinance
        +-- Tencent
        +-- Sina
        +-- EastMoney
        +-- SuperMind，可选，有账号再启用
```

## 5. 数据源职责

所有数据源都可以纳入 MCP，但不是每次请求都全部调用。MCP 根据字段、缓存、限流、可用性和质量策略自动决定调用哪些源。

| 数据源 | 主要用途 | 角色 |
| --- | --- | --- |
| AKShare | 行情、K线、财务、估值、板块、宏观、资金等 | 主力覆盖源 |
| Tushare | 财务、估值、行情关键字段、资金数据 | 独立验证源 |
| Baostock | A 股历史 K 线、复权因子 | 历史行情兜底源 |
| efinance | A 股行情、ETF、基础财务 | 轻量补充源 |
| 腾讯接口 | 实时行情、盘口、资金流 | 实时兜底源 |
| 新浪接口 | 实时行情、分钟/日 K 线 | 行情兜底源 |
| 东方财富 | 财务、板块、龙虎榜、资金流 | 深度补充源 |
| SuperMind | Tick、K线、回测、交易接口 | 可选增强源 |

SuperMind、Tushare 这类需要账号或 Token 的源，不影响 MCP 主流程。没有权限时自动跳过，并在结果里标记：

```json
{
  "provider": "tushare",
  "status": "disabled",
  "reason": "missing_token"
}
```

## 6. Tool 设计

### 6.1 get_workflow_data_bundle

这是 workflow 优先使用的主工具。

```text
get_workflow_data_bundle(
  symbols,
  fields,
  start_date=null,
  end_date=null,
  adjust="qfq",
  quality_policy="best_effort"
)
```

用途：

- 一次性获取 workflow 运行需要的数据包。
- 内部自动拆分为行情、K线、财务、估值、资金流等子任务。
- 内部自动多源补全和校验。
- 返回每只股票的完整数据、字段覆盖率和质量标签。

返回示例：

```json
{
  "ok": true,
  "data": {
    "symbols": {
      "sh600519": {
        "quote": {},
        "kline_daily": [],
        "valuation": {},
        "financial": {},
        "money_flow": {},
        "sector": {}
      }
    }
  },
  "quality": {
    "overall_confidence": "medium",
    "requested_fields": 42,
    "filled_fields": 36,
    "missing_fields": ["northbound_holding", "pledge_ratio"],
    "conflict_fields": [],
    "low_confidence_fields": ["money_flow.main_net_inflow"]
  },
  "sources": ["akshare", "tushare", "baostock", "tencent"],
  "warnings": []
}
```

### 6.2 get_realtime_quote

```text
get_realtime_quote(symbols, validate=true)
```

用途：

- 获取当前价格、涨跌幅、成交量、成交额、换手率、PE/PB、盘口等。
- 优先服务结果页和观察池刷新。

推荐内部路由：

```text
AKShare -> Tencent -> Sina -> efinance
```

### 6.3 get_kline

```text
get_kline(symbol, period="daily", start_date=null, end_date=null, adjust="qfq", validate=true)
```

用途：

- 获取日 K、周 K、月 K、分钟 K。
- 服务均线、趋势、波动率、复盘收益。

推荐内部路由：

```text
AKShare -> Baostock -> Tushare -> Sina -> EastMoney
```

### 6.4 get_financial_indicators

```text
get_financial_indicators(symbol, report_period=null, fields=null, validate=true)
```

用途：

- 获取营收、净利润、ROE、ROA、毛利率、净利率、资产负债率、经营现金流等。
- 服务基本面、成长性、盈利质量评分。

推荐内部路由：

```text
AKShare -> Tushare -> efinance -> EastMoney
```

### 6.5 get_valuation

```text
get_valuation(symbol, date=null, fields=null, validate=true)
```

用途：

- 获取 PE、PB、PS、股息率、市值、历史估值分位等。
- 服务估值筛选和估值评分。

推荐内部路由：

```text
AKShare -> Tushare -> Tencent -> efinance -> EastMoney
```

### 6.6 get_money_flow

```text
get_money_flow(symbol, date=null, window="1d", validate=true)
```

用途：

- 获取主力资金净流入、散户净流入、资金净流入占比。
- 服务资金面评分。

推荐内部路由：

```text
AKShare -> Tushare -> Tencent -> EastMoney
```

### 6.7 validate_stock_data

```text
validate_stock_data(symbol, fields, date=null, period=null)
```

用途：

- 对指定字段做多源验证。
- 适合 workflow 对关键候选股进行复核。

注意：这个工具不是让 Agent 手动做所有验证。默认情况下，`get_workflow_data_bundle` 内部已经会做必要验证。这个工具用于单独排查某个字段为什么低可信或冲突。

## 7. 统一返回结构

所有工具都应该返回统一 envelope：

```json
{
  "ok": true,
  "data": {},
  "coverage": {
    "requested_fields": 20,
    "filled_fields": 17,
    "missing_fields": ["pledge_ratio", "northbound_holding"]
  },
  "quality": {
    "confidence": "medium",
    "validated_fields": ["close", "volume", "pe", "pb"],
    "conflict_fields": [],
    "low_confidence_fields": ["money_flow"]
  },
  "sources": [
    {
      "provider": "akshare",
      "status": "ok",
      "used_fields": ["close", "volume", "pe", "pb"]
    },
    {
      "provider": "tushare",
      "status": "ok",
      "used_fields": ["revenue", "net_profit"]
    }
  ],
  "warnings": [],
  "errors": []
}
```

这个结构解决三个问题：

- workflow 知道拿到了哪些数据。
- workflow 知道哪些字段缺失。
- workflow 知道哪些字段可信度不足。

## 8. 股票代码规范

内部统一使用：

```text
sh600000
sz000001
bj430047
hk00700
usAAPL
```

适配器内部转换为各数据源需要的格式：

| 数据源 | 示例 |
| --- | --- |
| 新浪 | `sh600000`, `sz000001` |
| 腾讯 | `sh600000`, `sz000001` |
| Tushare | `600000.SH`, `000001.SZ` |
| Baostock | `sh.600000`, `sz.000001` |
| AKShare | 按具体接口转换 |

## 9. 多源补全策略

MCP 不应该只信一个源。推荐按字段做补全：

```text
请求字段集合
    |
    v
AKShare 先取一批
    |
    v
缺什么字段，就找其他 provider 补
    |
    v
关键字段用独立来源验证
    |
    v
合并成 workflow 数据包
```

字段补全示例：

| 字段 | 优先源 | 补充源 |
| --- | --- | --- |
| 日 K | AKShare | Baostock、Tushare、新浪、东方财富 |
| 当前价 | AKShare | 腾讯、新浪、efinance |
| PE/PB | AKShare | Tushare、腾讯、东方财富 |
| 营收/净利润 | AKShare | Tushare、东方财富、efinance |
| ROE/毛利率 | AKShare | Tushare、东方财富 |
| 资金流 | AKShare | 腾讯、东方财富、Tushare |
| 板块/行业 | AKShare | 东方财富 |

## 10. 多源校验策略

校验分 4 层，但都在 MCP 内部完成。

### 10.1 第一层：基础合法性校验

每个 provider 返回后先做基础检查：

```text
股票代码是否匹配
日期是否匹配
字段是否为空
数值类型是否正确
单位是否统一
币种是否统一
复权方式是否一致
是否停牌日
是否明显异常值
```

### 10.2 第二层：字段标准化校验

把不同源字段统一成 MCP 标准字段：

```text
成交量：手/股统一
成交额：万元/元统一
利润：万元/元统一
百分比：0.15 / 15% 统一
日期：YYYY-MM-DD 统一
```

### 10.3 第三层：独立来源偏差校验

对关键字段做多源对比：

| 类别 | 字段 | 异常阈值 |
| --- | --- | --- |
| 行情 | 收盘价 | 绝对偏差 > 0.01 元 |
| 行情 | 成交量 | 相对偏差 > 5% |
| 估值 | PE | 相对偏差 > 5% |
| 估值 | PB | 相对偏差 > 5% |
| 财务 | 净利润 | 相对偏差 > 3% |
| 财务 | 营业收入 | 相对偏差 > 3% |
| 财务 | ROE | 相对偏差 > 5% |
| 财务 | 毛利率 | 相对偏差 > 5% |
| 资金 | 主力净流入 | 相对偏差 > 10% |

### 10.4 第四层：可信度生成

可信度规则：

| 等级 | 条件 |
| --- | --- |
| high | 至少 3 个独立来源，偏差在阈值内 |
| medium | 2 个独立来源，偏差在阈值内 |
| low | 只有 1 个来源，或来源同源严重 |
| conflict | 多源差异超过阈值 |
| missing | 无有效数据 |

## 11. 同源降权

不能简单按“调用了几个库”计票，因为有些库底层可能来自同一网站。

建议给 provider 配置 `source_family`：

```json
{
  "akshare": "mixed",
  "tushare": "tushare",
  "baostock": "baostock",
  "efinance": "eastmoney",
  "eastmoney": "eastmoney",
  "tencent": "tencent",
  "sina": "sina",
  "supermind": "supermind"
}
```

计票规则：

```text
同一 source_family 的多个 provider 可保留原始值
但计算独立来源数量时只算一票
若同源内部都不一致，记录 provider 解析异常
```

## 12. 缓存与限流

### 12.1 缓存策略

| 数据类型 | 建议 TTL |
| --- | --- |
| 实时行情 | 5-30 秒 |
| 分钟 K 线 | 1-5 分钟 |
| 日 K 线 | 6-24 小时 |
| 财务报表 | 1-7 天 |
| 估值指标 | 1 天 |
| 股票池 | 1 天 |
| 数据源状态 | 1-5 分钟 |

建议本地先用：

```text
diskcache + SQLite
```

### 12.2 限流策略

按 provider 配置限流：

```yaml
providers:
  akshare:
    min_interval_ms: 100
    batch_size: 100
  tushare:
    min_interval_ms: 200
    batch_size: 100
  baostock:
    min_interval_ms: 100
    batch_size: 100
  efinance:
    min_interval_ms: 100
    batch_size: 100
  tencent:
    min_interval_ms: 120
    batch_size: 80
  sina:
    min_interval_ms: 120
    batch_size: 80
  eastmoney:
    min_interval_ms: 300
    batch_size: 50
```

遇到失败时：

```text
超时 -> 重试一次 -> 切换 provider
403/风控 -> provider 短时间熔断
解析失败 -> 记录错误，切换 provider
字段缺失 -> 进入补全流程
多源冲突 -> 标记 conflict，不静默覆盖
```

## 13. 数据库设计

建议在现有 SQLite 基础上增加这些表。

### 13.1 provider_status

| 字段 | 说明 |
| --- | --- |
| provider | 数据源名称 |
| status | healthy / degraded / down / disabled |
| last_success_at | 最近成功时间 |
| last_error_at | 最近失败时间 |
| last_error | 最近错误 |
| avg_latency_ms | 平均响应耗时 |

### 13.2 data_cache

| 字段 | 说明 |
| --- | --- |
| cache_key | 缓存键 |
| data_type | quote / kline / financial / valuation / money_flow |
| payload | JSON 数据 |
| source | 来源 |
| confidence | 可信度 |
| expires_at | 过期时间 |
| created_at | 创建时间 |

### 13.3 data_quality_log

| 字段 | 说明 |
| --- | --- |
| id | 主键 |
| symbol | 股票代码 |
| field | 字段 |
| date | 数据日期 |
| final_value | 最终值 |
| confidence | 可信度 |
| status | passed / conflict / missing |
| sources | 各来源原始值 JSON |
| max_deviation | 最大偏差 |
| threshold | 阈值 |
| created_at | 创建时间 |

### 13.4 workflow_data_snapshot

保存每次 workflow 运行时 MCP 返回的数据快照，方便复盘时知道当时用的是什么数据。

| 字段 | 说明 |
| --- | --- |
| id | 主键 |
| run_id | workflow run id |
| symbol | 股票代码 |
| payload | MCP 返回的数据包 |
| coverage | 字段覆盖情况 |
| quality | 质量信息 |
| sources | 数据来源 |
| created_at | 创建时间 |

## 14. 项目结构建议

```text
mcp_server/
  __init__.py
  __main__.py
  server.py
  config.py
  schemas.py
  providers/
    __init__.py
    base.py
    akshare_provider.py
    tushare_provider.py
    baostock_provider.py
    efinance_provider.py
    tencent_provider.py
    sina_provider.py
    eastmoney_provider.py
    supermind_provider.py
  services/
    __init__.py
    field_planner.py
    router.py
    normalizer.py
    merger.py
    quality_checker.py
    cache.py
    rate_limiter.py
  tools/
    __init__.py
    bundle.py
    market.py
    financial.py
    validation.py
  resources.py
  prompts.py
tests/
  test_symbol_normalizer.py
  test_quote_schema.py
  test_quality_checker.py
  test_provider_fallback.py
  test_bundle_contract.py
```

职责边界：

- `providers`：只负责调用外部数据源。
- `services`：负责路由、标准化、补全、校验、缓存、限流。
- `tools`：只负责 MCP tool 入参出参，不堆复杂业务逻辑。
- `schemas.py`：定义统一 Pydantic 模型。

## 15. 配置设计

### 15.1 环境变量

```text
TUSHARE_TOKEN=xxxx
SUPERMIND_TOKEN=xxxx
STOCK_MCP_CACHE_DIR=.cache/stock_mcp
STOCK_MCP_DB_PATH=data/stock_data.db
STOCK_MCP_DEFAULT_MARKET=A股
STOCK_MCP_QUALITY_POLICY=best_effort
```

### 15.2 Provider 配置

```yaml
providers:
  akshare:
    enabled: true
    priority: 10
    source_family: mixed
  tushare:
    enabled: true
    priority: 20
    source_family: tushare
    token_env: TUSHARE_TOKEN
  baostock:
    enabled: true
    priority: 30
    source_family: baostock
  efinance:
    enabled: true
    priority: 40
    source_family: eastmoney
  tencent:
    enabled: true
    priority: 50
    source_family: tencent
  sina:
    enabled: true
    priority: 60
    source_family: sina
  eastmoney:
    enabled: true
    priority: 70
    source_family: eastmoney
  supermind:
    enabled: false
    priority: 5
    source_family: supermind
    token_env: SUPERMIND_TOKEN
```

## 16. 与 Workflow 的关系

workflow 调 MCP 获取数据：

```text
workflow_engine
    -> get_workflow_data_bundle
    -> factor_engine
    -> score_engine
    -> result storage
```

MCP 不负责打分。它只返回：

```text
标准化数据
字段覆盖率
缺失字段
冲突字段
低可信字段
数据来源
数据时间戳
```

workflow 根据 MCP 结果做业务决策：

```text
字段缺失 -> 跳过该因子或降低评分可信度
字段 conflict -> 不参与核心评分，提示数据冲突
confidence low -> 可参与辅助展示，不参与关键决策
confidence high/medium -> 可进入正常评分
```

## 17. 合规提示

MCP 和 workflow 输出必须坚持中性表达：

- 使用“候选股票”“观察池”“入选原因”“风险提示”。
- 避免“推荐买入”“稳赚”“必涨”“交易信号”等表达。
- 所有数据保留来源、时间戳和可信度。
- 对低可信或冲突数据明确标记。
- 股票投资风险由用户自行承担，系统只做数据分析辅助。

## 18. 最终建议

这个 MCP 应该一步到位地设计成 workflow 的 best-effort 数据层：

```text
外部多数据源
    -> 自动路由
    -> 自动取数
    -> 自动补全
    -> 自动校验
    -> 自动标记质量
    -> 返回 workflow 可消费的数据包
```

外部调用方式保持简单：

```text
workflow 调一次 MCP
MCP 内部尽力拿全、尽力校验
workflow 根据质量标签使用数据
```

这样既满足“力所能及下最精确、最全面”，也不会把复杂度丢给 Agent 或 workflow。
