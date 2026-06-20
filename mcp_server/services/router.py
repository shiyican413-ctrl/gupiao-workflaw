"""
Provider Router —— 按 priority 路由到可用 provider，支持故障切换与多源采集。

设计要点：
    - _init_providers 根据 PROVIDER_CONFIG 的 enabled 标志按需实例化 provider。
    - get_providers 按 priority 升序返回可用 provider 列表（数值越小越优先）。
    - route 顺序尝试，命中第一个无 error 的结果即返回；全部失败抛 RuntimeError。
    - route_all 并行调用全部可用 provider，供 QualityChecker 做多源交叉验证。
"""

import logging
import time

logger = logging.getLogger(__name__)

DATA_TYPE_PROVIDERS = {
    "quote": {"akshare", "efinance", "tencent", "sina"},
    "kline": {"akshare", "baostock", "efinance"},
    "financial": {"akshare", "tushare", "baostock"},
    "valuation": {"akshare", "tushare"},
    "money_flow": {"akshare", "eastmoney"},
    "sector": {"akshare", "eastmoney"},
    "status": None,
}


class ProviderRouter:
    """按优先级路由到可用 provider，支持故障切换和手动指定源。"""

    def __init__(self, providers_config: dict):
        # name -> provider instance
        self._providers: dict = {}
        self._config: dict = providers_config
        self._init_providers()

    def _init_providers(self):
        """根据配置初始化 enabled 的 providers。"""
        # 延迟导入，避免 providers 尚未完全加载时引发循环依赖。
        from ..providers import (
            get_akshare_provider,
            get_baostock_provider,
            get_efinance_provider,
            get_sina_provider,
            get_tencent_provider,
            get_eastmoney_provider,
            get_tushare_provider,
        )

        # factory 注册表（顺序仅用于可读性；实际调度顺序由 priority 决定）
        provider_factories = [
            ("akshare", get_akshare_provider),
            ("tushare", get_tushare_provider),
            ("baostock", get_baostock_provider),
            ("efinance", get_efinance_provider),
            ("tencent", get_tencent_provider),
            ("sina", get_sina_provider),
            ("eastmoney", get_eastmoney_provider),
        ]

        for name, factory in provider_factories:
            cfg = self._config.get(name, {})
            if not cfg.get("enabled", True):
                continue
            try:
                self._providers[name] = factory()
            except Exception as e:  # 初始化失败不应阻断其它 provider
                logger.warning(f"初始化 {name} 失败: {e}")

    def get_providers(self, data_type: str) -> list:
        """返回 [(provider_name, priority), ...]，按 priority 升序排序。"""
        allowed = DATA_TYPE_PROVIDERS.get(data_type)
        providers = self._providers.items()
        if allowed is not None:
            providers = [(name, provider) for name, provider in providers if name in allowed]
        return sorted(
            providers,
            key=lambda x: self._config.get(x[0], {}).get("priority", 99),
        )

    def route(self, data_type: str, method_name: str, *args, **kwargs) -> dict:
        """
        路由到第一个成功的 provider。

        Returns:
            {"provider": str, "latency_ms": int, "data": Any, "warnings": list}
        Raises:
            RuntimeError: 所有 provider 均失败。
        """
        errors = []
        for name, _priority in self.get_providers(data_type):
            provider = self._providers[name]
            method = getattr(provider, method_name, None)
            if method is None:
                errors.append(f"{name}: 无方法 {method_name}")
                continue
            try:
                t0 = time.time()
                result = method(*args, **kwargs)
                latency = int((time.time() - t0) * 1000)
                if result is None:
                    errors.append(f"{name}: 返回 None")
                    continue
                if result.error is not None:
                    errors.append(f"{name}: {result.error}")
                    continue
                return {
                    "provider": name,
                    "source_family": getattr(result, "source_family", "") or self._config.get(name, {}).get("source_family", name),
                    "latency_ms": latency,
                    "data": result.data,
                    "warnings": getattr(result, "warnings", []) or [],
                }
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:100]}")
                continue
        raise RuntimeError(
            f"所有 provider 均失败（{data_type}/{method_name}）: {'; '.join(errors)}"
        )

    def route_all(self, data_type: str, method_name: str, *args, **kwargs) -> list:
        """
        从所有可用 provider 获取数据，用于多源验证。

        Returns:
            [{"provider": str, "latency_ms": int, "data": Any, "warnings": list}, ...]
            失败的 provider 用 "error" 字段替代 "data"/"warnings"。
        """
        results = []
        for name, _priority in self.get_providers(data_type):
            provider = self._providers[name]
            method = getattr(provider, method_name, None)
            if method is None:
                results.append({
                    "provider": name,
                    "latency_ms": 0,
                    "data": None,
                    "error": f"无方法 {method_name}",
                })
                continue
            try:
                t0 = time.time()
                result = method(*args, **kwargs)
                latency = int((time.time() - t0) * 1000)
                if result is None:
                    results.append({
                        "provider": name,
                        "latency_ms": latency,
                        "data": None,
                        "error": "返回 None",
                    })
                    continue
                if result.error is not None:
                    results.append({
                        "provider": name,
                        "latency_ms": latency,
                        "data": None,
                        "error": result.error,
                    })
                    continue
                results.append({
                    "provider": name,
                    "source_family": getattr(result, "source_family", "") or self._config.get(name, {}).get("source_family", name),
                    "latency_ms": latency,
                    "data": result.data,
                    "warnings": getattr(result, "warnings", []) or [],
                })
            except Exception as e:
                results.append({
                    "provider": name,
                    "latency_ms": 0,
                    "data": None,
                    "error": f"{type(e).__name__}: {str(e)[:100]}",
                })
        return results
