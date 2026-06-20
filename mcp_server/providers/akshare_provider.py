"""AkShare 数据源适配器。

只负责调用 akshare 库获取数据，返回统一格式的半标准化数据。
所有依赖（akshare）使用 lazy import，避免启动时拉依赖。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    """安全转 float。处理百分号字符串、None、'-'、空字符串等。"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or s in ("-", "--", "nan", "NaN", "None"):
            return default
        # 去掉百分号（仅去尾部百分号，不动小数点）
        if s.endswith("%"):
            s = s[:-1].strip()
        try:
            return float(s)
        except (ValueError, TypeError):
            return default
    return default


def _split_symbol(symbol: str) -> tuple[str, str]:
    """把 'sh600000' 拆成 (纯代码, 市场)。

    返回示例：('600000', 'sh')
    """
    symbol = (symbol or "").lower().strip()
    if symbol.startswith(("sh", "sz", "bj")):
        return symbol[2:], symbol[:2]
    return symbol, ""


def _compact_date(value: str | None, default: str) -> str:
    if not value:
        return default
    return str(value).replace("-", "")[:8]


class AkShareProvider(BaseProvider):
    name = "akshare"
    source_family = "mixed"

    def health_check(self) -> bool:
        try:
            import akshare as ak  # noqa: F401
            return True
        except Exception as e:  # pragma: no cover
            logger.warning("akshare health_check failed: %s", e)
            return False

    # ---------------- 实时行情 ----------------
    def get_realtime_quotes(self, symbols: list[str]) -> ProviderResult:
        start = time.time()
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))
            # 标准化 symbol 列做过滤
            if "代码" in df.columns:
                df = df.copy()
                df["__sym"] = df["代码"].astype(str).str.zfill(6)
                want = {s[2:] if s.lower().startswith(("sh", "sz", "bj")) else s for s in (symbols or [])}
                df = df[df["__sym"].isin(want)]

            results: list[dict] = []
            for _, row in df.iterrows():
                code = str(row.get("代码", "")).zfill(6)
                market = "sh" if code.startswith("6") else ("bj" if code.startswith(("4", "8")) else "sz")
                results.append({
                    "symbol": f"{market}{code}",
                    "name": row.get("名称"),
                    "price": _safe_float(row.get("最新价")),
                    "open": _safe_float(row.get("今开")),
                    "pre_close": _safe_float(row.get("昨收")),
                    "high": _safe_float(row.get("最高")),
                    "low": _safe_float(row.get("最低")),
                    "volume": _safe_float(row.get("成交量")),
                    "amount": _safe_float(row.get("成交额")),
                    "pct_change": _safe_float(row.get("涨跌幅")),
                    "change": _safe_float(row.get("涨跌额")),
                    "turnover_rate": _safe_float(row.get("换手率")),
                    "pe": _safe_float(row.get("市盈率-动态")),
                    "pb": _safe_float(row.get("市净率")),
                    "total_mv": _safe_float(row.get("总市值")),
                    "circ_mv": _safe_float(row.get("流通市值")),
                })
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_realtime_quotes error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- K线 ----------------
    def get_kline(self, symbol: str, period: str = "daily",
                  start_date: str = "20200101", end_date: str = "20261231",
                  adjust: str = "qfq", limit: Optional[int] = None) -> ProviderResult:
        start = time.time()
        try:
            import akshare as ak
            code, market = _split_symbol(symbol)
            start_date = _compact_date(start_date, "20200101")
            end_date = _compact_date(end_date, "20261231")

            # 分钟线走另一个接口
            if period in ("1m", "5m", "15m", "30m", "60m", "1", "5", "15", "30", "60"):
                period_map = {"1": "1", "5": "5", "15": "15", "30": "30", "60": "60",
                              "1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60"}
                p = period_map.get(period, "5")
                df = ak.stock_zh_a_hist_min_em(symbol=code, period=p, adjust=adjust)
            else:
                freq_map = {"daily": "daily", "d": "daily",
                            "weekly": "weekly", "w": "weekly",
                            "monthly": "monthly", "m": "monthly"}
                freq = freq_map.get(period, "daily")
                df = ak.stock_zh_a_hist(symbol=code, period=freq,
                                        start_date=start_date, end_date=end_date, adjust=adjust)

            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))

            results: list[dict] = []
            for _, row in df.iterrows():
                d = str(row.get("日期") or row.get("时间") or "")
                results.append({
                    "datetime": d,
                    "date": d[:10] if len(d) >= 10 else d,
                    "open": _safe_float(row.get("开盘")),
                    "high": _safe_float(row.get("最高")),
                    "low": _safe_float(row.get("最低")),
                    "close": _safe_float(row.get("收盘")),
                    "volume": _safe_float(row.get("成交量")),
                    "amount": _safe_float(row.get("成交额")),
                    "turnover_rate": _safe_float(row.get("换手率")),
                })

            if limit and limit > 0:
                results = results[-limit:]
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_kline error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- 财务 ----------------
    def get_financials(self, symbol: str) -> ProviderResult:
        start = time.time()
        warnings: list[str] = []
        out: dict = {"symbol": symbol}
        try:
            import akshare as ak
            code, _ = _split_symbol(symbol)

            # 同花顺财务摘要
            try:
                fa = ak.stock_financial_abstract_ths(symbol=code)
                if fa is not None and len(fa) > 0:
                    latest = fa.iloc[0].to_dict()
                    out["revenue_yoy"] = _safe_float(latest.get("营业总收入同比增长率"))
                    out["net_profit_yoy"] = _safe_float(latest.get("净利润同比增长率"))
                    out["roe"] = _safe_float(latest.get("净资产收益率-摊薄"))
                    out["debt_ratio"] = _safe_float(latest.get("资产负债率"))
                    out["net_margin"] = _safe_float(latest.get("销售净利率"))
                    out["ocf_per_share"] = _safe_float(latest.get("每股经营经营现金流", latest.get("每股经营现金流")))
                    out["report_date"] = str(latest.get("报告期", latest.get("数据日期", "")))
                else:
                    warnings.append("financial_abstract_ths empty")
            except Exception as e:
                warnings.append(f"financial_abstract_ths failed: {e}")

            # 百度估值
            try:
                val = ak.stock_zh_valuation_baidu(symbol=code, indicator="总市值", period="近一年")
                if val is not None and len(val) > 0:
                    last = val.iloc[-1].to_dict()
                    out["total_mv"] = _safe_float(last.get("value"))
            except Exception as e:
                warnings.append(f"valuation_baidu failed: {e}")

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=out, warnings=warnings,
                                  latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_financials error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), warnings=warnings,
                                  latency_ms=int((time.time() - start) * 1000))

    # ---------------- 估值 ----------------
    def get_valuation(self, symbol: str) -> ProviderResult:
        start = time.time()
        out: dict = {"symbol": symbol}
        warnings: list[str] = []
        try:
            import akshare as ak
            code, _ = _split_symbol(symbol)

            for indicator, key in (("市盈率(TTM)", "pe_ttm"),
                                   ("市净率", "pb"),
                                   ("市销率(TTM)", "ps_ttm"),
                                   ("股息率", "dividend_yield")):
                try:
                    df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period="近一年")
                    if df is not None and len(df) > 0:
                        out[key] = _safe_float(df.iloc[-1].get("value"))
                    else:
                        out[key] = None
                except Exception as e:
                    out[key] = None
                    warnings.append(f"{indicator} failed: {e}")

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=out, warnings=warnings,
                                  latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_valuation error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), warnings=warnings,
                                  latency_ms=int((time.time() - start) * 1000))

    # ---------------- 资金流 ----------------
    def get_money_flow(self, symbol: str, days: int = 30) -> ProviderResult:
        start = time.time()
        try:
            import akshare as ak
            code, market = _split_symbol(symbol)
            market_flag = market if market else ("sh" if code.startswith("6") else "sz")

            df = ak.stock_individual_fund_flow(stock=code, market=market_flag)
            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))

            if days and days > 0:
                df = df.tail(days)

            results: list[dict] = []
            for _, row in df.iterrows():
                results.append({
                    "date": str(row.get("日期", "")),
                    "close": _safe_float(row.get("收盘价")),
                    "pct_change": _safe_float(row.get("涨跌幅")),
                    "net_main": _safe_float(row.get("主力净流入-净额", row.get("主力净流入额"))),
                    "net_main_pct": _safe_float(row.get("主力净流入-净占比", row.get("主力净流入占比"))),
                    "net_super_large": _safe_float(row.get("超大单净流入-净额", row.get("超大单净流入额"))),
                    "net_large": _safe_float(row.get("大单净流入-净额", row.get("大单净流入额"))),
                    "net_medium": _safe_float(row.get("中单净流入-净额", row.get("中单净流入额"))),
                    "net_small": _safe_float(row.get("小单净流入-净额", row.get("小单净流入额"))),
                })
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data={"symbol": symbol, "flows": results},
                                  latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_money_flow error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- 指数成分股 ----------------
    def get_index_constituents(self, index_code: str) -> ProviderResult:
        start = time.time()
        try:
            import akshare as ak
            # 接受 "000300" 或 "sh000300" 两种格式
            idx = index_code.lower()
            if idx.startswith(("sh", "sz")):
                idx = idx[2:]

            df = ak.index_stock_cons(symbol=f"000300" if idx == "300" else idx)
            if df is None or len(df) == 0:
                # 尝试带前缀
                df = ak.index_stock_cons(symbol=idx)
            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))

            results: list[dict] = []
            for _, row in df.iterrows():
                code = str(row.get("品种代码", row.get("代码", ""))).zfill(6)
                market = "sh" if code.startswith("6") else "sz"
                results.append({
                    "symbol": f"{market}{code}",
                    "code": code,
                    "name": row.get("品种名称", row.get("名称")),
                })
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_index_constituents error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- 板块 ----------------
    def get_sectors(self) -> ProviderResult:
        start = time.time()
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            if df is None or len(df) == 0:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      error="empty data", latency_ms=int((time.time() - start) * 1000))

            results: list[dict] = []
            for _, row in df.iterrows():
                results.append({
                    "name": row.get("板块名称"),
                    "code": str(row.get("板块代码", "")),
                    "pct_change": _safe_float(row.get("涨跌幅")),
                    "turnover_rate": _safe_float(row.get("换手率")),
                    "net_amount": _safe_float(row.get("主力净流入额", row.get("上涨股数"))),
                    "leader_stock": row.get("领涨股票"),
                    "leader_pct": _safe_float(row.get("领涨股票-涨跌幅")),
                })
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("akshare get_sectors error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))
