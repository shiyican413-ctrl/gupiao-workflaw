"""
统一数据模型（Pydantic）。

约定：
    - 股票代码内部统一使用 sh600000 / sz000001 / bj430047 格式（小写市场前缀 + 6 位数字）。
    - 所有模型均可独立序列化（model_dump / model_dump_json）。
    - 字段 confidence 取值范围：
        high    —— 多源验证一致
        normal  —— 单源或基本可信
        medium  —— 部分缺失或时效一般
        low     —— 数据稀疏或来源单一且不可信
        conflict—— 多源冲突
        missing —— 字段缺失
    - warnings 用于承载校验/缺失/冲突等告警信息。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# 行情
# ============================================================
class StockQuote(BaseModel):
    """实时/盘后行情快照。"""

    symbol: str                       # sh600000
    name: str
    price: float
    open: float
    pre_close: float
    high: float
    low: float
    volume: float                     # 成交量（股）
    amount: float                     # 成交额（元）
    pct_change: float                 # 涨跌幅 %
    turnover_rate: float              # 换手率 %
    pe: float                         # 市盈率
    pb: float                         # 市净率
    timestamp: str                    # 数据时间点（各源格式不一，统一字符串）
    source: str = ""
    confidence: str = "normal"        # high/normal/medium/low/conflict/missing
    validated: bool = False
    warnings: list[str] = Field(default_factory=list)


# ============================================================
# K 线
# ============================================================
class KlineBar(BaseModel):
    """单根 K 线。"""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0
    turnover_rate: float = 0.0


class KlineResult(BaseModel):
    """K 线查询结果。"""

    symbol: str
    period: str                       # daily / weekly / monthly / 1m / 5m ...
    adjust: str                       # qfq / hfq / none
    items: list[KlineBar] = Field(default_factory=list)
    source: str = ""
    confidence: str = "normal"
    warnings: list[str] = Field(default_factory=list)


# ============================================================
# 财务
# ============================================================
class FinancialIndicator(BaseModel):
    """财务指标（单期）。金额单位：亿元；比率单位：%。"""

    symbol: str
    report_date: str = ""
    revenue: float = 0                # 营业收入（亿元）
    net_profit: float = 0             # 净利润（亿元）
    revenue_growth: float = 0         # 营收同比增长率 %
    profit_growth: float = 0          # 净利润同比增长率 %
    gross_margin: float = 0           # 毛利率 %
    net_margin: float = 0             # 净利率 %
    roe: float = 0                    # ROE %
    roa: float = 0
    debt_ratio: float = 0             # 资产负债率 %
    operating_cashflow: float = 0     # 经营现金流（亿元，正数）
    pe_ttm: float = 0
    pb: float = 0
    ps_ttm: float = 0
    dividend_yield: float = 0
    source: str = ""
    confidence: str = "normal"
    validated: bool = False
    warnings: list[str] = Field(default_factory=list)


# ============================================================
# 估值
# ============================================================
class ValuationData(BaseModel):
    """估值快照。"""

    symbol: str
    pe: float = 0
    pb: float = 0
    ps: float = 0
    dividend_yield: float = 0
    market_cap: float = 0             # 总市值（亿元）
    circulating_cap: float = 0        # 流通市值（亿元）
    pe_percentile: float = 0          # 历史分位（0-100）
    source: str = ""
    confidence: str = "normal"
    warnings: list[str] = Field(default_factory=list)


# ============================================================
# 资金流向
# ============================================================
class MoneyFlowItem(BaseModel):
    """单日资金流向。金额单位：万元。"""

    date: str
    main_net_inflow: float            # 主力净流入（万元）
    retail_net_inflow: float = 0      # 散户净流入（万元）
    net_inflow_ratio: float = 0       # 资金净流入占比 %
    turnover_rate: float = 0
    north_flow: float = 0             # 北向资金（万元）


class MoneyFlowResult(BaseModel):
    """资金流向查询结果。"""

    symbol: str
    items: list[MoneyFlowItem] = Field(default_factory=list)
    source: str = ""
    confidence: str = "normal"


# ============================================================
# 交叉验证
# ============================================================
class ValidationSource(BaseModel):
    """参与验证的单一来源贡献。"""

    provider: str
    source_family: str
    value: float
    status: str                       # ok / error / timeout


class ValidationResult(BaseModel):
    """某字段在某标的上的交叉验证结果。"""

    symbol: str
    field: str
    date: str = ""
    final_value: float
    confidence: str                   # high/medium/low/conflict/missing
    status: str                       # passed / conflict / missing
    max_deviation: float = 0
    threshold: float = 0
    sources: list[ValidationSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ============================================================
# 选股结果
# ============================================================
class ScreenStocksResult(BaseModel):
    """
    选股结果。

    candidates 元素结构示例：
        {
            "symbol": "sh600519",
            "name": "贵州茅台",
            "industry": "白酒",
            "scores": {"value": 80, "growth": 70, "quality": 85, "momentum": 60},
            "reasons": ["ROE 持续 > 20%", "估值低于行业均值"],
            "risks": ["短期资金流出"],
            "confidence": "high",
        }
    summary 结构示例：
        {
            "total": 10,
            "filters_applied": [...],
            "strategy": "价值+成长",
            "as_of": "2026-06-21",
        }
    """

    candidates: list[dict] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    source: str = ""
    warnings: list[str] = Field(default_factory=list)


# ============================================================
# 统一响应封装
# ============================================================
class ResponseEnvelope(BaseModel):
    """
    对外统一响应封装。

    - ok:       本次请求是否成功
    - data:     业务数据（dict / list / None）
    - meta:     元信息，例如：
                    request_id, source, source_policy, cache_hit,
                    timestamp, confidence, warnings
    - errors:   错误信息列表（ok=False 时通常非空）
    """

    ok: bool
    data: Optional[Any] = None
    meta: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
