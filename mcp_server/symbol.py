"""
股票代码规范化与格式互转。

内部统一格式：sh600000 / sz000001 / bj430047
    - 小写市场前缀（sh / sz / bj）
    - 6 位数字代码

支持的输入格式示例（normalize_symbol 均能识别）：
    600000 / 000001 / 430047
    600000.SH / 000001.SZ / 430047.BJ
    sh600000 / sz000001 / bj430047
    SH.600000 / SZ.000001
"""

from __future__ import annotations


def normalize_symbol(raw: str) -> str:
    """
    将任意格式的股票代码转为 sh600000 / sz000001 / bj430047 格式。

    规则：
        - 去除前后空白、统一大写后再处理市场前缀
        - 去除 .SH / .SZ / .BJ 以及 . / - / 空白
        - 688xxx、6xxxxx => 沪市（sh）
        - 300xxx / 301xxx / 00xxxx / 30xxxx => 深市（sz）
        - 8xxxxx / 4xxxxx => 北交所（bj）
        - 非纯数字（如 ETF 简称）原样返回
        - 默认归到深市

    Args:
        raw: 原始股票代码字符串。

    Returns:
        规范化后的股票代码（小写前缀 + 6 位数字），或非数字原值。
    """
    if raw is None:
        return ""
    code = str(raw).strip().upper()
    # 去除市场后缀与前缀可能的点号、连字符、空白
    code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "").replace(".", "")
    code = code.replace("-", "").replace(" ", "")
    # 若以 SH/SZ/BJ 开头，去掉前缀，仅保留数字部分统一判定
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    if not code.isdigit():
        # 非纯数字代码（如 ETF 名称）原样返回（保留原始大小写已为大写）
        return code
    code6 = code.zfill(6)
    if code6.startswith("688"):
        return f"sh{code6}"
    elif code6.startswith("300") or code6.startswith("301"):
        return f"sz{code6}"
    elif code6.startswith("6"):
        return f"sh{code6}"
    elif code6.startswith(("00", "30")):
        return f"sz{code6}"
    elif code6.startswith("8") or code6.startswith("4"):
        return f"bj{code6}"
    return f"sz{code6}"  # 默认


def to_akshare_code(symbol: str) -> str:
    """
    sh600000 -> 600000

    AKShare 不同接口对代码格式要求不一，这里统一返回 6 位纯数字码，
    调用方在具体接口处可再作拼接（如 'sh' + code 或带市场后缀）。
    """
    if not isinstance(symbol, str) or len(symbol) < 2:
        return symbol or ""
    return symbol[2:].zfill(6)


def to_baostock_code(symbol: str) -> str:
    """
    sh600000 -> sh.600000 （Baostock 标准格式）

    输入已是内部格式 sh600000，转换为 Baostock 要求的 sh.600000。
    """
    if not isinstance(symbol, str) or len(symbol) < 2:
        return symbol or ""
    market = symbol[:2].lower()
    digits = symbol[2:].zfill(6)
    return f"{market}.{digits}"


def to_sina_code(symbol: str) -> str:
    """
    sh600000 -> sh600000 （新浪格式）
    """
    if not isinstance(symbol, str) or len(symbol) < 2:
        return symbol or ""
    return f"{symbol[:2].lower()}{symbol[2:].zfill(6)}"


def to_tencent_code(symbol: str) -> str:
    """
    sh600000 -> sh600000 （腾讯格式）
    """
    if not isinstance(symbol, str) or len(symbol) < 2:
        return symbol or ""
    return f"{symbol[:2].lower()}{symbol[2:].zfill(6)}"


def to_tushare_code(symbol: str) -> str:
    """
    sh600000 -> 600000.SH
    sz000001 -> 000001.SZ
    bj430047 -> 430047.BJ
    """
    if not isinstance(symbol, str) or len(symbol) < 2:
        return symbol or ""
    market = symbol[:2].upper()
    digits = symbol[2:].zfill(6)
    if market == "SH":
        return f"{digits}.SH"
    elif market == "SZ":
        return f"{digits}.SZ"
    elif market == "BJ":
        return f"{digits}.BJ"
    # 未知市场默认按 SH 处理（与 normalize_symbol 默认深市不同：此处保守返回原值）
    return f"{digits}.{market}"


def guess_market(symbol: str) -> str:
    """
    根据内部格式代码推测所属市场板块（中文描述）。

    Returns:
        科创板 / 创业板 / 沪市主板 / 深市主板 / 北交所 / 其他
    """
    if not isinstance(symbol, str) or len(symbol) < 4:
        return "其他"
    prefix = symbol[:2].lower()
    seg = symbol[2:4]
    if prefix == "sh" and seg == "68":
        return "科创板"
    elif prefix == "sz" and seg in ("30",):
        return "创业板"
    elif prefix == "sh":
        return "沪市主板"
    elif prefix == "sz":
        return "深市主板"
    elif prefix == "bj":
        return "北交所"
    return "其他"


def format_symbol_display(symbol: str) -> str:
    """
    sh600000 -> 600000 （展示用纯数字代码）
    """
    if not isinstance(symbol, str):
        return ""
    return symbol[2:] if len(symbol) > 2 else symbol
