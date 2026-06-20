"""
Cache Manager —— 两级缓存：进程内 L1（dict） + 磁盘 L2（diskcache）。

设计要点：
    - L1 命中即返回，零 IO；未命中查 L2 并回填 L1。
    - TTL 按 data_type 区分（来自 config.CACHE_TTL），不同数据新鲜度要求不同。
    - 线程安全：L1 使用 threading.Lock 保护；diskcache 自身线程/进程安全。
    - invalidate 同时清理 L1 与 L2，用于强制刷新场景。
"""

import threading
import time

from diskcache import Cache as DiskCache

from ..config import CACHE_DIR, CACHE_TTL


class CacheManager:
    """两层缓存：内存 L1 + diskcache L2。"""

    def __init__(self):
        # cache_key -> (timestamp, value)
        self._mem: dict = {}
        self._lock = threading.Lock()
        # 确保缓存目录存在
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._disk: DiskCache = DiskCache(str(CACHE_DIR))

    def get(self, cache_key: str, data_type: str):
        """命中返回值，未命中返回 None。"""
        ttl = CACHE_TTL.get(data_type, 300)

        # L1
        with self._lock:
            item = self._mem.get(cache_key)
            if item is not None:
                ts, value = item
                if time.time() - ts <= ttl:
                    return value
                # 过期，淘汰
                self._mem.pop(cache_key, None)

        # L2
        val = self._disk.get(cache_key)
        if val is not None:
            self._set_mem(cache_key, val)
            return val
        return None

    def set(self, cache_key: str, value, data_type: str) -> None:
        """写入 L1 与 L2，L2 带 expire。"""
        ttl = CACHE_TTL.get(data_type, 300)
        self._disk.set(cache_key, value, expire=ttl)
        self._set_mem(cache_key, value)

    def invalidate(self, cache_key: str) -> None:
        """同时清理 L1 与 L2 中指定 key。"""
        with self._lock:
            self._mem.pop(cache_key, None)
        try:
            del self._disk[cache_key]
        except KeyError:
            pass

    def _set_mem(self, key, value) -> None:
        with self._lock:
            self._mem[key] = (time.time(), value)
