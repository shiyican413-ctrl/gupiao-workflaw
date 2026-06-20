from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ProviderResult(BaseModel):
    """Provider 的统一返回。"""
    data: list[dict] | dict | None = None
    error: Optional[str] = None
    source: str = ""
    source_family: str = ""
    cached: bool = False
    latency_ms: int = 0
    warnings: list[str] = Field(default_factory=list)


class BaseProvider(ABC):
    """所有数据源的基类。"""
    name: str = ""
    source_family: str = ""

    @abstractmethod
    def health_check(self) -> bool:
        """快速检查数据源是否可用。"""
        ...
