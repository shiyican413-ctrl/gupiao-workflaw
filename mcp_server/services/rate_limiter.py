"""
Rate Limiter —— per-provider 最小调用间隔限流，防止高频请求被封。

设计要点：
    - 每个 provider 维护上次调用时间戳；间隔不足即视为需要等待。
    - check 为非阻塞：返回 False 表示当前不可调用（调用方自行决定降级/排队）。
    - wait_if_needed 为阻塞：必要时 sleep 到满足间隔后再返回。
    - 配置项 min_interval_ms 来自 PROVIDER_CONFIG，默认 200ms。
"""

import threading
import time


class RateLimiter:
    """Per-provider 限流器，防止高频请求被封。"""

    def __init__(self, provider_config: dict):
        # provider_name -> 上次调用时间戳
        self._last_call: dict = {}
        self._lock = threading.Lock()
        self._config: dict = provider_config

    def check(self, provider_name: str) -> bool:
        """
        非阻塞检查。返回 True 表示可以立即调用，False 表示需要等待。
        注意：返回 True 时会占用本次配额（更新 last_call）。
        """
        cfg = self._config.get(provider_name, {})
        min_interval = cfg.get("min_interval_ms", 200) / 1000.0
        with self._lock:
            last = self._last_call.get(provider_name, 0.0)
            now = time.time()
            if now - last < min_interval:
                return False
            self._last_call[provider_name] = now
            return True

    def wait_if_needed(self, provider_name: str) -> None:
        """如果距上次调用不足最小间隔，则阻塞等待，然后更新时间戳。"""
        cfg = self._config.get(provider_name, {})
        min_interval = cfg.get("min_interval_ms", 200) / 1000.0
        with self._lock:
            last = self._last_call.get(provider_name, 0.0)
            wait = min_interval - (time.time() - last)
            if wait > 0:
                # 释放锁后再 sleep，避免阻塞其它 provider 的限流判断
                pass
            else:
                wait = 0
                self._last_call[provider_name] = time.time()
        if wait > 0:
            time.sleep(wait)
            with self._lock:
                self._last_call[provider_name] = time.time()
