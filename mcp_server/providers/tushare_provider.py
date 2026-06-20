"""Tushare 数据源适配器。

注意：Tushare 需要有效 token，旧版接口已停运。本 provider 健康检查在
无 token / 接口不可用时会返回 False，方法返回带 error 的 ProviderResult。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _split_symbol(symbol: str) -> tuple[str, str]:
    s = (symbol or "").lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s[2:], s[:2]
    return s, ""


def _ts_code(symbol: str) -> str:
    """把 'sh600519' 转成 tushare 的 '600519.SH'。"""
    code, market = _split_symbol(symbol)
    if not market:
        market = "sh" if code.startswith("6") else ("bj" if code.startswith(("4", "8")) else "sz")
    return f"{code.upper()}.{market.upper()}"


class TushareProvider(BaseProvider):
    name = "tushare"
    source_family = "tushare"

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token or os.getenv("TUSHARE_TOKEN") or ""
        self._api = None

    def _get_api(self):
        if self._api is not None:
            return self._api
        if not self._token:
            return None
        try:
            import tushare as ts  # noqa
            ts.set_token(self._token)
            self._api = ts.pro_api()
            return self._api
        except Exception as e:
            logger.warning("tushare init failed: %s", e)
            return None

    def health_check(self) -> bool:
        api = self._get_api()
        if api is None:
            return False
        try:
            api.trade_cal(exchange="", start_date="20250101", end_date="20250102")
            return True
        except Exception as e:
            logger.warning("tushare health_check failed: %s", e)
            return False

    # ---------------- 财务 ----------------
    def get_financials(self, symbol: str, period: str = "20241231") -> ProviderResult:
        start = time.time()
        try:
            api = self._get_api()
            if api is None:
                return ProviderResult(
                    source=self.name, source_family=self.source_family,
                    error="tushare token unavailable",
                    latency_ms=int((time.time() - start) * 1000),
                )

            ts_code = _ts_code(symbol)
            out: dict = {"symbol": symbol, "ts_code": ts_code, "period": period}
            warnings: list[str] = []

            try:
                fin = api.income(ts_code=ts_code, period=period)
                if fin is not None and len(fin) > 0:
                    row = fin.iloc[0]
                    out["revenue"] = _safe_float(row.get("total_revenue"))
                    out["net_profit"] = _safe_float(row.get("n_income"))
                else:
                    warnings.append("income empty")
            except Exception as e:
                warnings.append(f"income failed: {e}")

            try:
                fin = api.fina_indicator(ts_code=ts_code, period=period)
                if fin is not None and len(fin) > 0:
                    row = fin.iloc[0]
                    out["roe"] = _safe_float(row.get("roe"))
                    out["net_margin"] = _safe_float(row.get("net_profit_margin"))
                    out["gross_margin"] = _safe_float(row.get("grossprofit_margin"))
                    out["debt_ratio"] = _safe_float(row.get("debt_to_assets"))
                    out["q_profit_yoy"] = _safe_float(row.get("q_profit_yoy"))
                    out["or_yoy"] = _safe_float(row.get("or_yoy"))
                else:
                    warnings.append("fina_indicator empty")
            except Exception as e:
                warnings.append(f"fina_indicator failed: {e}")

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=out, warnings=warnings,
                                  latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("tushare get_financials error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- 估值 ----------------
    def get_valuation(self, symbol: str, trade_date: Optional[str] = None) -> ProviderResult:
        start = time.time()
        try:
            api = self._get_api()
            if api is None:
                return ProviderResult(
                    source=self.name, source_family=self.source_family,
                    error="tushare token unavailable",
                    latency_ms=int((time.time() - start) * 1000),
                )

            ts_code = _ts_code(symbol)
            out: dict = {"symbol": symbol, "ts_code": ts_code}

            try:
                daily = api.daily_basic(ts_code=ts_code, trade_date=trade_date,
                                        fields="ts_code,trade_date,pe,pb,ps,dv_ratio,pe_ttm,total_mv,circ_mv")
                if daily is not None and len(daily) > 0:
                    row = daily.iloc[0]
                    out["trade_date"] = str(row.get("trade_date", ""))
                    out["pe"] = _safe_float(row.get("pe"))
                    out["pe_ttm"] = _safe_float(row.get("pe_ttm"))
                    out["pb"] = _safe_float(row.get("pb"))
                    out["ps"] = _safe_float(row.get("ps"))
                    out["dividend_yield"] = _safe_float(row.get("dv_ratio"))
                    out["total_mv"] = _safe_float(row.get("total_mv"))
                    out["circ_mv"] = _safe_float(row.get("circ_mv"))
                else:
                    out["error_detail"] = "daily_basic empty"
            except Exception as e:
                out["error_detail"] = str(e)

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=out, warnings=[] if "error_detail" not in out else [out["error_detail"]],
                                  latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("tushare get_valuation error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))
