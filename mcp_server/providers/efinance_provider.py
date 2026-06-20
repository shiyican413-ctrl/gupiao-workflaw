"""Efinance 数据源适配器（东方财富源）。

只负责调用 efinance 库。返回统一格式。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or s in ("-", "--", "nan", "NaN"):
            return default
        if s.endswith("%"):
            s = s[:-1].strip()
        try:
            return float(s)
        except (ValueError, TypeError):
            return default
    return default


def _split_symbol(symbol: str) -> tuple[str, str]:
    s = (symbol or "").lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s[2:], s[:2]
    return s, ""


class EfinanceProvider(BaseProvider):
    name = "efinance"
    source_family = "eastmoney"

    def health_check(self) -> bool:
        try:
            import efinance as ef  # noqa: F401
            return True
        except Exception as e:
            logger.warning("efinance health_check failed: %s", e)
            return False

    # ---------------- 实时行情 ----------------
    def get_realtime_quotes(self, symbols: list[str]) -> ProviderResult:
        start = time.time()
        try:
            import efinance as ef
            df = ef.stock.get_realtime_quotes()
            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))

            want_codes = {_split_symbol(s)[0] for s in (symbols or [])}
            code_col = "股票代码" if "股票代码" in df.columns else "代码"
            name_col = "股票名称" if "股票名称" in df.columns else "名称"

            if want_codes:
                df = df.copy()
                df["__code"] = df[code_col].astype(str)
                df = df[df["__code"].isin(want_codes)]

            results: list[dict] = []
            for _, row in df.iterrows():
                code = str(row.get(code_col, "")).zfill(6)
                market = "sh" if code.startswith("6") else ("bj" if code.startswith(("4", "8")) else "sz")
                results.append({
                    "symbol": f"{market}{code}",
                    "code": code,
                    "name": row.get(name_col),
                    "price": _safe_float(row.get("最新价", row.get("现价"))),
                    "open": _safe_float(row.get("今开", row.get("开盘"))),
                    "pre_close": _safe_float(row.get("昨收")),
                    "high": _safe_float(row.get("最高")),
                    "low": _safe_float(row.get("最低")),
                    "volume": _safe_float(row.get("成交量")),
                    "amount": _safe_float(row.get("成交额")),
                    "pct_change": _safe_float(row.get("涨跌幅")),
                    "change": _safe_float(row.get("涨跌额")),
                    "turnover_rate": _safe_float(row.get("换手率")),
                    "pe": _safe_float(row.get("市盈率(动态)", row.get("市盈率"))),
                    "pb": _safe_float(row.get("市净率")),
                    "total_mv": _safe_float(row.get("总市值")),
                    "circ_mv": _safe_float(row.get("流通市值")),
                })
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("efinance get_realtime_quotes error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- K线 ----------------
    def get_kline(self, symbol: str, period: str = "daily",
                  start_date: Optional[str] = None, end_date: Optional[str] = None,
                  adjust: str = "qfq", limit: Optional[int] = None) -> ProviderResult:
        start = time.time()
        try:
            import efinance as ef
            code, _ = _split_symbol(symbol)

            # kctypes: 1=日, 5=5分, 15=15分, 30=30分, 60=60分, 2=周, 3=月 (efinance 沿用东财代码)
            kct_map = {
                "daily": 1, "d": 1,
                "weekly": 2, "w": 2,
                "monthly": 3, "m": 3,
                "5m": 5, "5": 5,
                "15m": 15, "15": 15,
                "30m": 30, "30": 30,
                "60m": 60, "60": 60,
            }
            kct = kct_map.get(period, 1)

            df = ef.stock.get_quote_history(code, klt=kct, fqt=int(1 if adjust == "qfq" else (2 if adjust == "hfq" else 0)))
            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))

            date_col = "日期" if "日期" in df.columns else "时间"

            results: list[dict] = []
            for _, row in df.iterrows():
                d = str(row.get(date_col, ""))
                results.append({
                    "datetime": d,
                    "date": d[:10] if len(d) >= 10 else d,
                    "open": _safe_float(row.get("开盘")),
                    "close": _safe_float(row.get("收盘")),
                    "high": _safe_float(row.get("最高")),
                    "low": _safe_float(row.get("最低")),
                    "volume": _safe_float(row.get("成交量")),
                    "amount": _safe_float(row.get("成交额")),
                    "turnover_rate": _safe_float(row.get("换手率")),
                    "pct_change": _safe_float(row.get("涨跌幅")),
                    "change": _safe_float(row.get("涨跌额")),
                })

            if start_date:
                results = [r for r in results if r["date"] >= start_date[:10]]
            if end_date:
                results = [r for r in results if r["date"] <= end_date[:10]]
            if limit and limit > 0:
                results = results[-limit:]

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("efinance get_kline error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))
