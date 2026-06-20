"""
股票选股 MCP Server
====================

基于 FastMCP 框架构建的 A 股选股工具服务，采用 stdio 传输协议。

数据源（Provider）包括：
    - AKShare
    - Baostock
    - efinance
    - 新浪（Sina）
    - 腾讯（Tencent）
    - 东方财富（Eastmoney）
    - Tushare（可选，需 Token）

子模块说明：
    - config:      全局配置、路径锚定、缓存 TTL、Provider 配置、验证阈值
    - schemas:     统一数据模型（Pydantic），如行情、K 线、财务、估值、资金流等
    - symbol:      股票代码规范化与各数据源格式互转
    - providers:   各数据源适配器实现
    - services:    数据获取、缓存、交叉验证、选股等核心业务逻辑
    - tools:       暴露给 MCP 客户端的工具（tool）定义

内部股票代码统一格式：sh600000 / sz000001 / bj430047。
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
