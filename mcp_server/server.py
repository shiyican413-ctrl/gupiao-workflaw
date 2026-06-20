"""FastMCP 入口。

对外暴露的是 workflow 需要的统一数据工具；多源取数、补全、校验都在
StockDataService 内部完成。
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from . import __version__
from .services.stock_data import StockDataService


service = StockDataService()

mcp = FastMCP(
    name="stock-workflow-data-mcp",
    version=__version__,
    instructions=(
        "为选股 Workflow 提供 best-effort 股票数据。"
        "调用方只需要请求统一工具，MCP 内部会自动多源取数、补全、校验，"
        "并返回 coverage、quality、sources、warnings。"
    ),
)


@mcp.tool
def get_workflow_data_bundle(
    symbols: list[str],
    fields: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
    quality_policy: str = "best_effort",
    limit: int | None = 120,
) -> dict[str, Any]:
    """一次性获取 workflow 运行需要的数据包。

    fields 可选值：quote、kline_daily、valuation、financial、money_flow、sector。
    """
    return service.get_workflow_data_bundle(
        symbols=symbols,
        fields=fields,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
        quality_policy=quality_policy,
        limit=limit,
    )


@mcp.tool
def get_realtime_quote(symbols: list[str], validate: bool = True) -> dict[str, Any]:
    """获取实时行情快照，内部自动多源兜底和关键字段校验。"""
    return service.get_realtime_quote(symbols=symbols, validate=validate)


@mcp.tool
def get_kline(
    symbol: str,
    period: str = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
    validate: bool = True,
    limit: int | None = 120,
) -> dict[str, Any]:
    """获取 K 线数据，默认日 K 前复权。"""
    return service.get_kline(
        symbol=symbol,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
        validate=validate,
        limit=limit,
    )


@mcp.tool
def get_financial_indicators(symbol: str, validate: bool = True) -> dict[str, Any]:
    """获取核心财务指标并返回质量标签。"""
    return service.get_financial_indicators(symbol=symbol, validate=validate)


@mcp.tool
def get_valuation(symbol: str, validate: bool = True) -> dict[str, Any]:
    """获取估值指标并返回质量标签。"""
    return service.get_valuation(symbol=symbol, validate=validate)


@mcp.tool
def get_money_flow(symbol: str, validate: bool = True, days: int = 30) -> dict[str, Any]:
    """获取资金流向数据。"""
    return service.get_money_flow(symbol=symbol, validate=validate, days=days)


@mcp.tool
def validate_stock_data(
    symbol: str,
    fields: list[str],
    date: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """单独验证指定字段，常用于排查低可信或冲突字段。"""
    return service.validate_stock_data(symbol=symbol, fields=fields, date=date, period=period)


@mcp.resource("stock://providers")
def provider_status() -> dict[str, Any]:
    """当前已启用 provider 配置摘要。"""
    return service.provider_status()


@mcp.resource("stock://schema/quality")
def quality_schema() -> dict[str, Any]:
    """quality 字段说明。"""
    return {
        "confidence": {
            "high": "至少 3 个独立来源且偏差在阈值内",
            "medium": "2 个独立来源且偏差在阈值内，或字段有部分缺失",
            "low": "只有单源数据或来源独立性不足",
            "conflict": "多源差异超过阈值",
            "missing": "无有效数据",
        },
        "fields": ["validated_fields", "conflict_fields", "low_confidence_fields", "missing_fields"],
    }


def main() -> None:
    """启动 stdio MCP server。"""
    mcp.run()


if __name__ == "__main__":
    main()

