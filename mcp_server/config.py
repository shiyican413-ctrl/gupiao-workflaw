"""
全局配置模块。

负责：
    - 路径锚定（项目根、数据库、缓存目录）
    - 环境变量读取
    - 缓存 TTL 配置
    - Provider（数据源）启用/优先级/限速/批量配置
    - 交叉验证阈值

本模块只导出常量与配置字典，不依赖项目内其它模块，可被任意模块安全导入。
"""

import os
from pathlib import Path

# ============================================================
# 路径锚定
# ============================================================
# config.py 位于 mcp_server/ 下，PROJECT_ROOT 指向其上一级（即项目根目录）
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
DB_PATH: Path = Path(os.getenv("STOCK_MCP_DB_PATH", str(DATA_DIR / "stock_data.db")))
CACHE_DIR: Path = Path(os.getenv("STOCK_MCP_CACHE_DIR", str(PROJECT_ROOT / ".cache" / "stock_mcp")))

# ============================================================
# 环境变量
# ============================================================
TUSHARE_TOKEN: str = os.getenv("TUSHARE_TOKEN", "")
DEFAULT_MARKET: str = os.getenv("STOCK_MCP_DEFAULT_MARKET", "A股")

# ============================================================
# 缓存 TTL（秒）
# ============================================================
# 按数据类型设定不同的过期时间，兼顾时效性与数据源压力。
CACHE_TTL = {
    "realtime_quote": 10,          # 实时行情：10 秒
    "kline_minute": 60,            # 分钟 K 线：1 分钟
    "kline_daily": 6 * 3600,       # 日 K 线：6 小时
    "financial": 24 * 3600,        # 财务指标：24 小时
    "valuation": 24 * 3600,        # 估值数据：24 小时
    "money_flow": 60,              # 资金流向：1 分钟
    "sector": 24 * 3600,           # 板块数据：24 小时
    "index_constituents": 7 * 86400,  # 指数成分股：7 天
    "stock_pool": 24 * 3600,       # 选股结果池：24 小时
    "provider_status": 300,        # Provider 健康状态：5 分钟
}

# ============================================================
# Provider（数据源）配置
# ============================================================
# - enabled:        是否启用
# - priority:       优先级（数值越小越优先；同样数据优先调用数值小者）
# - source_family:  数据源家族（用于交叉验证时的同类合并/剔除）
# - min_interval_ms: 最小调用间隔（毫秒），用于限速
# - batch_size:     批量请求的推荐批量大小
PROVIDER_CONFIG = {
    "akshare": {
        "enabled": True,
        "priority": 10,
        "source_family": "mixed",
        "min_interval_ms": 100,
        "batch_size": 100,
    },
    "tushare": {
        "enabled": True,
        "priority": 20,
        "source_family": "tushare",
        "min_interval_ms": 200,
        "batch_size": 100,
    },
    "baostock": {
        "enabled": True,
        "priority": 30,
        "source_family": "baostock",
        "min_interval_ms": 200,
        "batch_size": 50,
    },
    "efinance": {
        "enabled": True,
        "priority": 40,
        "source_family": "eastmoney",
        "min_interval_ms": 200,
        "batch_size": 50,
    },
    "tencent": {
        "enabled": True,
        "priority": 50,
        "source_family": "tencent",
        "min_interval_ms": 120,
        "batch_size": 80,
    },
    "sina": {
        "enabled": True,
        "priority": 60,
        "source_family": "sina",
        "min_interval_ms": 120,
        "batch_size": 80,
    },
    "eastmoney": {
        "enabled": True,
        "priority": 70,
        "source_family": "eastmoney",
        "min_interval_ms": 300,
        "batch_size": 50,
    },
}

# ============================================================
# 交叉验证阈值
# ============================================================
# - type: "absolute" 绝对差值阈值；"relative" 相对差值阈值（比例）
# - threshold:
#     * absolute => |a - b| <= threshold 视为一致
#     * relative => |a - b| / max(|a|, |b|) <= threshold 视为一致
VALIDATION_THRESHOLDS = {
    "close": {"type": "absolute", "threshold": 0.01},
    "volume": {"type": "relative", "threshold": 0.05},
    "pe": {"type": "relative", "threshold": 0.05},
    "pb": {"type": "relative", "threshold": 0.05},
    "net_profit": {"type": "relative", "threshold": 0.03},
    "revenue": {"type": "relative", "threshold": 0.03},
    "roe": {"type": "relative", "threshold": 0.05},
    "gross_margin": {"type": "relative", "threshold": 0.05},
}
