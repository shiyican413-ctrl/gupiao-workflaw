"""东方财富数据源适配器（HTTP 直连）。

提供：资金流、板块列表。
secid 规则：sz -> 0.<code>，sh -> 1.<code>。
"""
from __future__ import annotations

import logging
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


def _secid(symbol: str) -> str:
    """把 'sh600519' / 'sz000001' 转成东财 secid。"""
    s = (symbol or "").lower().strip()
    if s.startswith("sh"):
        return f"1.{s[2:]}"
    if s.startswith("sz") or s.startswith("bj"):
        return f"0.{s[2:]}"
    # 纯代码：6 开头是沪市
    if s.startswith("6"):
        return f"1.{s}"
    return f"0.{s}"


class EastmoneyProvider(BaseProvider):
    name = "eastmoney"
    source_family = "eastmoney"

    def health_check(self) -> bool:
        try:
            import requests
            url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
            params = {"secid": "1.600519", "fields1": "f1,f2,f3,f7",
                      "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                      "klt": "101", "lmt": "1"}
            resp = requests.get(url, params=params, timeout=5,
                                headers={"Referer": "https://quote.eastmoney.com/"})
            return resp.status_code == 200
        except Exception as e:
            logger.warning("eastmoney health_check failed: %s", e)
            return False

    # ---------------- 资金流 ----------------
    def get_money_flow(self, symbol: str, days: int = 30) -> ProviderResult:
        start = time.time()
        try:
            import requests

            secid = _secid(symbol)
            url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
            fields2 = ",".join(f"f{i}" for i in range(51, 64))
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": fields2,
                "klt": "101",  # 日K
                "lmt": str(max(int(days or 30), 1)),
            }
            headers = {"Referer": "https://quote.eastmoney.com/"}
            resp = requests.get(url, params=params, headers=headers, timeout=8)
            data = resp.json()

            klines = (data or {}).get("data", {}).get("klines") or []
            results: list[dict] = []
            for line in klines:
                parts = line.split(",")
                if len(parts) < 13:
                    continue
                # f51..f63 顺序大致为：
                # 日期,主力净流入,小单,中单,大单,超大单,主力净流入占比,...
                results.append({
                    "date": parts[0],
                    "net_main": _safe_float(parts[1]),
                    "net_small": _safe_float(parts[2]),
                    "net_medium": _safe_float(parts[3]),
                    "net_large": _safe_float(parts[4]),
                    "net_super_large": _safe_float(parts[5]),
                    "net_main_pct": _safe_float(parts[6]),
                })

            if days and days > 0:
                results = results[-days:]

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data={"symbol": symbol, "flows": results},
                                  latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("eastmoney get_money_flow error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))

    # ---------------- 板块 ----------------
    def get_sectors(self) -> ProviderResult:
        start = time.time()
        try:
            import requests

            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "f3",
                "sortTypes": "-1",
                "pageSize": "500",
                "pageNumber": "1",
                "reportName": "RPT_BOARD_INDUSTRY_PCT",
                "columns": "f12,f14,f3,f104,f128,f136",
                "source": "WEB",
                "client": "WEB",
            }
            headers = {"Referer": "https://quote.eastmoney.com/center/boardlist.html"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            payload = resp.json()

            rows = (payload or {}).get("result", {}).get("data") or []
            results: list[dict] = []
            for row in rows:
                results.append({
                    "code": row.get("f12"),
                    "name": row.get("f14"),
                    "pct_change": _safe_float(row.get("f3")),
                    "leader_stock": row.get("f128"),
                    "leader_pct": _safe_float(row.get("f136")),
                    "up_count": _safe_float(row.get("f104")),
                })

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("eastmoney get_sectors error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))
