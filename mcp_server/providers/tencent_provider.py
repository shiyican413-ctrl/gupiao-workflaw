"""腾讯财经实时行情适配器。

直接 HTTP 请求 https://qt.gtimg.cn/q=...
返回格式：v_sh600519="1~贵州茅台~600519~1800.00~..."（~分隔）
常用字段位置：3=当前价, 4=昨收, 5=今开, 6=成交量(手), 31=涨跌额,
32=涨跌幅, 33=最高, 34=最低, 37=成交额(万), 38=换手率,
39=市盈率, 44=总市值, 45=流通市值, 46=市净率。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

TENCENT_URL = "https://qt.gtimg.cn/q="


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class TencentProvider(BaseProvider):
    name = "tencent"
    source_family = "tencent"

    def health_check(self) -> bool:
        try:
            import requests
            headers = {"Referer": "https://gu.qq.com/"}
            resp = requests.get(TENCENT_URL + "sh000001", headers=headers, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("tencent health_check failed: %s", e)
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
                "Referer": "https://gu.qq.com/",
                "User-Agent": "Mozilla/5.0",
            }
            url = TENCENT_URL + ",".join(symbols)
            resp = requests.get(url, headers=headers, timeout=8)
            resp.encoding = "gbk"
            text = resp.text

            results: list[dict] = []
            for line in text.splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                try:
                    head, body = line.split("=", 1)
                    head = head.replace("v_", "").strip()
                    body = body.strip().strip(";").strip('"')
                    if not body:
                        continue
                    fields = body.split("~")
                    if len(fields) < 33:
                        continue
                    name = fields[1] if len(fields) > 1 else ""
                    price = _safe_float(fields[3])
                    pre_close = _safe_float(fields[4]) if len(fields) > 4 else None
                    open_p = _safe_float(fields[5]) if len(fields) > 5 else None
                    volume_lot = _safe_float(fields[6]) if len(fields) > 6 else None
                    change = _safe_float(fields[31]) if len(fields) > 31 else None
                    pct_change = _safe_float(fields[32]) if len(fields) > 32 else None
                    high = _safe_float(fields[33]) if len(fields) > 33 else None
                    low = _safe_float(fields[34]) if len(fields) > 34 else None
                    amount_wan = _safe_float(fields[37]) if len(fields) > 37 else None
                    turnover_rate = _safe_float(fields[38]) if len(fields) > 38 else None
                    pe = _safe_float(fields[39]) if len(fields) > 39 else None
                    total_mv = _safe_float(fields[44]) if len(fields) > 44 else None
                    circ_mv = _safe_float(fields[45]) if len(fields) > 45 else None
                    pb = _safe_float(fields[46]) if len(fields) > 46 else None

                    results.append({
                        "symbol": head,
                        "name": name,
                        "price": price,
                        "open": open_p,
                        "pre_close": pre_close,
                        "high": high,
                        "low": low,
                        "volume": volume_lot * 100 if volume_lot is not None else None,
                        "amount": amount_wan * 10000 if amount_wan is not None else None,
                        "change": change,
                        "pct_change": pct_change,
                        "turnover_rate": turnover_rate,
                        "pe": pe,
                        "pb": pb,
                        "total_mv": total_mv,
                        "circ_mv": circ_mv,
                    })
                except Exception as e:
                    logger.debug("tencent parse line failed: %s", e)
                    continue

            return ProviderResult(source=self.name, source_family=self.source_family,
                                  data=results, latency_ms=int((time.time() - start) * 1000))
        except Exception as e:
            logger.warning("tencent get_realtime_quotes error: %s", e)
            return ProviderResult(source=self.name, source_family=self.source_family,
                                  error=str(e), latency_ms=int((time.time() - start) * 1000))
