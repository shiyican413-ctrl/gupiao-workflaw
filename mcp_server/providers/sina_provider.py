"""新浪财经实时行情适配器。

直接 HTTP 请求 https://hq.sinajs.cn/list=...
字段位置（逗号分隔）：0=名称,1=今开,2=昨收,3=当前价,4=最高,5=最低,8=成交量,9=成交额
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

SINA_URL = "https://hq.sinajs.cn/list="


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class SinaProvider(BaseProvider):
    name = "sina"
    source_family = "sina"

    def health_check(self) -> bool:
        try:
            import requests
            headers = {"Referer": "https://finance.sina.com.cn",
                       "User-Agent": "Mozilla/5.0"}
            resp = requests.get(SINA_URL + "sh000001", headers=headers, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("sina health_check failed: %s", e)
            return False

    def get_realtime_quotes(self, symbols: list[str]) -> ProviderResult:
        start = time.time()
        try:
            import requests

            symbols = [s.lower().strip() for s in (symbols or []) if s]
            if not symbols:
                return ProviderResult(source=self.name, source_family=self.source_family,
                                      data=[], latency_ms=int((time.time() - start) * 1000))

            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0",
            }
            url = SINA_URL + ",".join(symbols)
            resp = requests.get(url, headers=headers, timeout=8)
            resp.encoding = "gbk"
            text = resp.text

            results: list[dict] = []
            for line in text.splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                # 形如：var hq_str_sh600519="贵州茅台,1800,...";
                try:
                    head, body = line.split("=", 1)
                    head = head.replace("var hq_str_", "").strip()
                    body = body.strip().strip(";").strip('"')
                    if not body:
                        continue
                    fields = body.split(",")
                    if len(fields) < 10:
                        continue
                    name = fields[0]
                    open_p = _safe_float(fields[1])
                    pre_close = _safe_float(fields[2])
                    price = _safe_float(fields[3])
                    high = _safe_float(fields[4])
                    low = _safe_float(fields[5])
                    volume = _safe_float(fields[8])
                    amount = _safe_float(fields[9])
                    pct_change = None
                    if price is not None and pre_close:
                        pct_change = round((price / pre_close - 1) * 100, 4)
                    results.append({
                        "symbol": head,
                        "name": name,
                        "price": price,
                        "open": open_p,
                        "pre_close": pre_close,
                        "high": high,
                        "low": low,
                        "volume": volume,
                        "amount": amount,
                        "pct_change": pct_change,
                        "change": round(price - pre_close, 4) if (price is not None and pre_close) else None,
                    })
                except Exception as e:
                    logger.debug("sina parse line failed: %s", e)
                    continue

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("sina get_realtime_quotes error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))
