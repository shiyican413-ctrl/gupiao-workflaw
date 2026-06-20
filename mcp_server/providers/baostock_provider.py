"""Baostock 数据源适配器。

只负责调用 baostock 库获取数据。每次查询必须 login + logout。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


def _baostock_symbol(symbol: str) -> str:
    """把 'sh600000' 转成 baostock 的 'sh.600000'。"""
    s = (symbol or "").lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return f"{s[:2]}.{s[2:]}"
    # 纯代码，按规则补市场前缀
    if s.startswith("6"):
        return f"sh.{s}"
    return f"sz.{s}"


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _dash_date(value: str | None, default: str) -> str:
    if not value:
        return default
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    compact = text.replace("-", "")[:8]
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return default


class BaostockProvider(BaseProvider):
    name = "baostock"
    source_family = "baostock"

    def health_check(self) -> bool:
        try:
            import baostock as bs
            lg = bs.login()
            ok = getattr(lg, "error_code", "0") == "0"
            bs.logout()
            return bool(ok)
        except Exception as e:
            logger.warning("baostock health_check failed: %s", e)
            return False

    # ---------------- K线 ----------------
    def get_kline(self, symbol: str, period: str = "daily",
                  start_date: str = "2025-01-01", end_date: str = "2026-12-31",
                  adjust: str = "qfq", limit: Optional[int] = None) -> ProviderResult:
        start = time.time()
        try:
            import baostock as bs

            bs_code = _baostock_symbol(symbol)
            start_date = _dash_date(start_date, "2025-01-01")
            end_date = _dash_date(end_date, "2026-12-31")
            freq_map = {"daily": "d", "d": "d",
                        "weekly": "w", "w": "w",
                        "monthly": "m", "m": "m"}
            frequency = freq_map.get(period, "d")

            adjust_map = {"qfq": "2", "2": "2",
                          "hfq": "1", "1": "1",
                          "none": "3", "3": "3", "": "3"}
            adjustflag = adjust_map.get(adjust, "2")

            fields = "date,open,high,low,close,volume,amount,turn"

            lg = bs.login()
            if getattr(lg, "error_code", "0") != "0":
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error=f"login failed: {getattr(lg, 'error_msg', '')}",
                                      latency_ms=int((time.time() - start) * 1000))
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code, fields,
                    start_date=start_date, end_date=end_date,
                    frequency=frequency, adjustflag=adjustflag,
                )
                if getattr(rs, "error_code", "0") != "0":
                    return ProviderResult(source=self.name, source_family=self.source_family,
                                          error=f"{getattr(rs, 'error_msg', '')}",
                                          latency_ms=int((time.time() - start) * 1000))

                results: list[dict] = []
                while rs.next():
                    row = rs.get_row_data()
                    # date, open, high, low, close, volume, amount, turn
                    results.append({
                        "date": row[0],
                        "datetime": row[0],
                        "open": _safe_float(row[1]),
                        "high": _safe_float(row[2]),
                        "low": _safe_float(row[3]),
                        "close": _safe_float(row[4]),
                        "volume": _safe_float(row[5]),
                        "amount": _safe_float(row[6]),
                        "turnover_rate": _safe_float(row[7]),
                    })

                if limit and limit > 0:
                    results = results[-limit:]

                return ProviderResult(source=self.name, source_family=self.source_family,
                                      data=results, latency_ms=int((time.time() - start) * 1000))
            finally:
                bs.logout()
        except Exception as e:
            logger.warning("baostock get_kline error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- 财务 ----------------
    def get_financials(self, symbol: str, year: int = 2024, quarter: int = 4) -> ProviderResult:
        start = time.time()
        warnings: list[str] = []
        out: dict = {"symbol": symbol, "year": year, "quarter": quarter}
        try:
            import baostock as bs

            bs_code = _baostock_symbol(symbol)
            lg = bs.login()
            if getattr(lg, "error_code", "0") != "0":
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error=f"login failed: {getattr(lg, 'error_msg', '')}",
                                      latency_ms=int((time.time() - start) * 1000))
            try:
                # 成长能力
                try:
                    rs = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
                    if getattr(rs, "error_code", "0") == "0":
                        while rs.next():
                            row = rs.get_row_data()
                            # code,pubDate,statDate,YOYEquity,YOYAsset,YOYNI,YOYEPSBasic
                            out["yoy_equity"] = _safe_float(row[3])
                            out["yoy_asset"] = _safe_float(row[4])
                            out["yoy_net_profit"] = _safe_float(row[5])
                            out["yoy_eps_basic"] = _safe_float(row[6])
                            out["pub_date"] = row[1]
                            out["stat_date"] = row[2]
                            break
                    else:
                        warnings.append(f"growth: {getattr(rs, 'error_msg', '')}")
                except Exception as e:
                    warnings.append(f"growth failed: {e}")

                # 盈利能力
                try:
                    rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
                    if getattr(rs, "error_code", "0") == "0":
                        while rs.next():
                            row = rs.get_row_data()
                            # code,pubDate,statDate,roeAvg,npMargin,gpMargin,netProfit,epsTTM,MBRevenue,totalShare,liqaShare
                            out["roe"] = _safe_float(row[3])
                            out["net_margin"] = _safe_float(row[4])
                            out["gross_margin"] = _safe_float(row[5])
                            out["net_profit"] = _safe_float(row[6])
                            out["eps_ttm"] = _safe_float(row[7])
                            break
                    else:
                        warnings.append(f"profit: {getattr(rs, 'error_msg', '')}")
                except Exception as e:
                    warnings.append(f"profit failed: {e}")

                return ProviderResult(source=self.name, source_family=self.source_family,
                                      data=out, warnings=warnings,
                                      latency_ms=int((time.time() - start) * 1000))
            finally:
                bs.logout()
        except Exception as e:
            logger.warning("baostock get_financials error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), warnings=warnings,
                                  latency_ms=int((time.time() - start) * 1000))
