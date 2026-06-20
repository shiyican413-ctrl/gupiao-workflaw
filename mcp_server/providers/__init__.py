"""providers 包：导出各数据源 provider 的实例化函数。

约定：
- 所有 provider 方法接收的 symbol 格式为 'sh600000' / 'sz000001'
- 每个 provider 只管调数据，不管缓存/路由/验证
- 每个方法返回 ProviderResult
"""
from .base import BaseProvider, ProviderResult
from .akshare_provider import AkShareProvider
from .baostock_provider import BaostockProvider
from .efinance_provider import EfinanceProvider
from .sina_provider import SinaProvider
from .tencent_provider import TencentProvider
from .eastmoney_provider import EastmoneyProvider
from .tushare_provider import TushareProvider

__all__ = [
    "BaseProvider",
    "ProviderResult",
    "get_akshare_provider",
    "get_baostock_provider",
    "get_efinance_provider",
    "get_sina_provider",
    "get_tencent_provider",
    "get_eastmoney_provider",
    "get_tushare_provider",
]


def get_akshare_provider() -> AkShareProvider:
    return AkShareProvider()


def get_baostock_provider() -> BaostockProvider:
    return BaostockProvider()


def get_efinance_provider() -> EfinanceProvider:
    return EfinanceProvider()


def get_sina_provider() -> SinaProvider:
    return SinaProvider()


def get_tencent_provider() -> TencentProvider:
    return TencentProvider()


def get_eastmoney_provider() -> EastmoneyProvider:
    return EastmoneyProvider()


def get_tushare_provider(token: str | None = None) -> TushareProvider:
    return TushareProvider(token=token)
