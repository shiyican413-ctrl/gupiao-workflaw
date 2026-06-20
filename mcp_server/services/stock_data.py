"""Best-effort 股票数据服务层。

这个模块承接 MCP tool 与 provider 之间的核心编排：
    - 一次 workflow 请求拆成 quote/kline/financial/valuation/money_flow 子任务
    - 调用多个 provider，按字段补全
    - 对关键字段做多源校验
    - 返回 coverage / quality / sources / warnings，供 workflow 决定如何使用数据
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..config import PROVIDER_CONFIG
from ..symbol import normalize_symbol
from .cache import CacheManager
from .quality_checker import QualityChecker
from .router import ProviderRouter


DEFAULT_BUNDLE_FIELDS = ["quote", "kline_daily", "valuation", "financial"]

SECTION_FIELDS = {
    "quote": ["price", "change", "pct_change", "volume", "amount", "turnover_rate", "pe", "pb"],
    "kline_daily": ["date", "open", "high", "low", "close", "volume", "amount"],
    "valuation": ["pe", "pb", "ps", "dividend_yield", "market_cap", "circulating_cap"],
    "financial": [
        "revenue",
        "net_profit",
        "revenue_growth",
        "profit_growth",
        "roe",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "operating_cashflow",
    ],
    "money_flow": ["main_net_inflow", "retail_net_inflow", "net_inflow_ratio"],
    "sector": ["industry", "concept"],
}

QUALITY_ORDER = {
    "high": 5,
    "normal": 4,
    "medium": 3,
    "low": 2,
    "missing": 1,
    "conflict": 0,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text in {"-", "--", "nan", "NaN", "None"}:
            return None
        if text.endswith("%"):
            text = text[:-1].strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _compact_date(value: str | None) -> str | None:
    if not value:
        return value
    return str(value).replace("-", "")[:8]


class StockDataService:
    """面向 workflow 的 best-effort 数据服务。"""

    def __init__(self) -> None:
        self.router = ProviderRouter(PROVIDER_CONFIG)
        self.cache = CacheManager()
        self.quality_checker = QualityChecker()

    # ------------------------------------------------------------------
    # Public API used by MCP tools
    # ------------------------------------------------------------------
    def get_workflow_data_bundle(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "qfq",
        quality_policy: str = "best_effort",
        limit: int | None = 120,
    ) -> dict:
        symbols = self._normalize_symbols(symbols)
        requested_sections = self._normalize_sections(fields)
        cache_key = self._cache_key(
            "bundle",
            symbols=symbols,
            fields=requested_sections,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            quality_policy=quality_policy,
            limit=limit,
        )
        cached = self.cache.get(cache_key, "stock_pool")
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        warnings: list[str] = []
        errors: list[str] = []
        source_events: list[dict] = []
        symbols_data: dict[str, dict] = {symbol: {} for symbol in symbols}
        symbol_quality: dict[str, dict] = {symbol: self._empty_quality() for symbol in symbols}

        if "quote" in requested_sections:
            quote_env = self.get_realtime_quote(symbols, validate=quality_policy != "fast")
            source_events.extend(quote_env.get("sources", []))
            warnings.extend(quote_env.get("warnings", []))
            errors.extend(quote_env.get("errors", []))
            for symbol, quote in (quote_env.get("data") or {}).items():
                symbols_data.setdefault(symbol, {})["quote"] = quote
                self._merge_quality(symbol_quality[symbol], quote_env.get("quality_by_symbol", {}).get(symbol, {}))

        for symbol in symbols:
            if "kline_daily" in requested_sections:
                kline_env = self.get_kline(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                    validate=quality_policy != "fast",
                    limit=limit,
                )
                source_events.extend(kline_env.get("sources", []))
                warnings.extend(kline_env.get("warnings", []))
                errors.extend(kline_env.get("errors", []))
                symbols_data[symbol]["kline_daily"] = kline_env.get("data", {}).get("items", [])
                self._merge_quality(symbol_quality[symbol], kline_env.get("quality", {}))

            if "valuation" in requested_sections:
                valuation_env = self.get_valuation(symbol=symbol, validate=quality_policy != "fast")
                source_events.extend(valuation_env.get("sources", []))
                warnings.extend(valuation_env.get("warnings", []))
                errors.extend(valuation_env.get("errors", []))
                symbols_data[symbol]["valuation"] = valuation_env.get("data", {})
                self._merge_quality(symbol_quality[symbol], valuation_env.get("quality", {}))

            if "financial" in requested_sections:
                financial_env = self.get_financial_indicators(symbol=symbol, validate=quality_policy != "fast")
                source_events.extend(financial_env.get("sources", []))
                warnings.extend(financial_env.get("warnings", []))
                errors.extend(financial_env.get("errors", []))
                symbols_data[symbol]["financial"] = financial_env.get("data", {})
                self._merge_quality(symbol_quality[symbol], financial_env.get("quality", {}))

            if "money_flow" in requested_sections:
                money_env = self.get_money_flow(symbol=symbol, validate=quality_policy != "fast")
                source_events.extend(money_env.get("sources", []))
                warnings.extend(money_env.get("warnings", []))
                errors.extend(money_env.get("errors", []))
                symbols_data[symbol]["money_flow"] = money_env.get("data", {}).get("items", [])
                self._merge_quality(symbol_quality[symbol], money_env.get("quality", {}))

            if "sector" in requested_sections:
                symbols_data[symbol]["sector"] = {}
                symbol_quality[symbol]["missing_fields"].append("sector.industry")
                symbol_quality[symbol]["missing_fields"].append("sector.concept")

        coverage = self._build_bundle_coverage(symbols_data, requested_sections)
        quality = self._build_bundle_quality(symbol_quality, coverage)
        data = {"symbols": symbols_data}

        envelope = self._envelope(
            ok=not bool(errors) or bool(symbols_data),
            data=data,
            coverage=coverage,
            quality=quality,
            quality_by_symbol=symbol_quality,
            sources=self._dedupe_sources(source_events),
            warnings=self._dedupe_strings(warnings),
            errors=self._dedupe_strings(errors),
        )
        self.cache.set(cache_key, envelope, "stock_pool")
        return envelope

    def get_realtime_quote(self, symbols: list[str], validate: bool = True) -> dict:
        symbols = self._normalize_symbols(symbols)
        cache_key = self._cache_key("quote", symbols=symbols, validate=validate)
        cached = self.cache.get(cache_key, "realtime_quote")
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        route_results = self.router.route_all("quote", "get_realtime_quotes", symbols)
        data_by_symbol: dict[str, dict] = {}
        quality_by_symbol: dict[str, dict] = {}
        warnings: list[str] = []

        for symbol in symbols:
            provider_items = self._extract_provider_items(route_results, symbol)
            merged, used_sources = self._merge_provider_dicts(provider_items, self._quote_field_map)
            merged.setdefault("symbol", symbol)
            merged["sources"] = used_sources
            quality = self._quality_for_provider_items(
                symbol=symbol,
                provider_items=provider_items,
                fields={"price": "close", "volume": "volume", "pe": "pe", "pb": "pb"} if validate else {},
            )
            merged["confidence"] = quality.get("confidence", "low")
            data_by_symbol[symbol] = merged
            quality_by_symbol[symbol] = quality
            warnings.extend(quality.get("warnings", []))

        coverage = self._build_section_coverage(data_by_symbol, "quote")
        quality = self._aggregate_quality(list(quality_by_symbol.values()), coverage)
        envelope = self._envelope(
            ok=bool(data_by_symbol),
            data=data_by_symbol,
            coverage=coverage,
            quality=quality,
            quality_by_symbol=quality_by_symbol,
            sources=self._source_summary(route_results),
            warnings=warnings,
            errors=self._route_errors(route_results),
        )
        self.cache.set(cache_key, envelope, "realtime_quote")
        return envelope

    def get_kline(
        self,
        symbol: str,
        period: str = "daily",
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "qfq",
        validate: bool = True,
        limit: int | None = 120,
    ) -> dict:
        symbol = normalize_symbol(symbol)
        cache_key = self._cache_key(
            "kline",
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            validate=validate,
            limit=limit,
        )
        cached = self.cache.get(cache_key, "kline_daily" if period in {"daily", "d"} else "kline_minute")
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        route_results = self.router.route_all(
            "kline",
            "get_kline",
            symbol,
            period,
            start_date or "20200101",
            end_date or _compact_date(_now_iso()[:10]) or "20261231",
            adjust,
            limit,
        )
        best = self._first_valid_route_data(route_results, expected_type=list)
        items = best.get("data", []) if best else []
        quality = self._empty_quality()
        if validate and items:
            latest_by_provider = []
            for result in route_results:
                rows = result.get("data")
                if result.get("error") or not isinstance(rows, list) or not rows:
                    continue
                latest = rows[-1]
                if _safe_float(latest.get("close")) is not None:
                    latest_by_provider.append({
                        "provider": result["provider"],
                        "source_family": result.get("source_family"),
                        "data": _safe_float(latest.get("close")),
                    })
            validation = self.quality_checker.validate_field("close", latest_by_provider)
            validation.symbol = symbol
            quality = self._quality_from_validations([validation.model_dump()])

        data = {
            "symbol": symbol,
            "period": period,
            "adjust": adjust,
            "items": items,
            "source": best.get("provider") if best else "",
        }
        coverage = self._build_single_section_coverage(items[-1] if items else {}, "kline_daily")
        envelope = self._envelope(
            ok=bool(items),
            data=data,
            coverage=coverage,
            quality=self._aggregate_quality([quality], coverage),
            sources=self._source_summary(route_results),
            warnings=quality.get("warnings", []),
            errors=self._route_errors(route_results) if not items else [],
        )
        self.cache.set(cache_key, envelope, "kline_daily" if period in {"daily", "d"} else "kline_minute")
        return envelope

    def get_financial_indicators(self, symbol: str, validate: bool = True) -> dict:
        symbol = normalize_symbol(symbol)
        cache_key = self._cache_key("financial", symbol=symbol, validate=validate)
        cached = self.cache.get(cache_key, "financial")
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        route_results = self.router.route_all("financial", "get_financials", symbol)
        provider_items = self._extract_single_provider_dicts(route_results, self._financial_field_map)
        merged, used_sources = self._merge_provider_dicts(provider_items, self._identity_map)
        merged["symbol"] = symbol
        merged["sources"] = used_sources
        validations = []
        if validate:
            validations = self._validate_fields_from_provider_items(
                symbol,
                provider_items,
                {"revenue": "revenue", "net_profit": "net_profit", "roe": "roe", "gross_margin": "gross_margin"},
            )
        quality = self._quality_from_validations(validations)
        coverage = self._build_single_section_coverage(merged, "financial")
        envelope = self._envelope(
            ok=bool(merged),
            data=merged,
            coverage=coverage,
            quality=self._aggregate_quality([quality], coverage),
            sources=self._source_summary(route_results),
            warnings=quality.get("warnings", []),
            errors=self._route_errors(route_results) if not provider_items else [],
        )
        self.cache.set(cache_key, envelope, "financial")
        return envelope

    def get_valuation(self, symbol: str, validate: bool = True) -> dict:
        symbol = normalize_symbol(symbol)
        cache_key = self._cache_key("valuation", symbol=symbol, validate=validate)
        cached = self.cache.get(cache_key, "valuation")
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        route_results = self.router.route_all("valuation", "get_valuation", symbol)
        provider_items = self._extract_single_provider_dicts(route_results, self._valuation_field_map)
        merged, used_sources = self._merge_provider_dicts(provider_items, self._identity_map)
        merged["symbol"] = symbol
        merged["sources"] = used_sources
        validations = []
        if validate:
            validations = self._validate_fields_from_provider_items(
                symbol,
                provider_items,
                {"pe": "pe", "pb": "pb"},
            )
        quality = self._quality_from_validations(validations)
        coverage = self._build_single_section_coverage(merged, "valuation")
        envelope = self._envelope(
            ok=bool(merged),
            data=merged,
            coverage=coverage,
            quality=self._aggregate_quality([quality], coverage),
            sources=self._source_summary(route_results),
            warnings=quality.get("warnings", []),
            errors=self._route_errors(route_results) if not provider_items else [],
        )
        self.cache.set(cache_key, envelope, "valuation")
        return envelope

    def get_money_flow(self, symbol: str, validate: bool = True, days: int = 30) -> dict:
        symbol = normalize_symbol(symbol)
        cache_key = self._cache_key("money_flow", symbol=symbol, validate=validate, days=days)
        cached = self.cache.get(cache_key, "money_flow")
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        route_results = self.router.route_all("money_flow", "get_money_flow", symbol, days)
        best = self._first_valid_route_data(route_results, expected_type=dict)
        raw_items = (best.get("data", {}) or {}).get("flows", []) if best else []
        items = [self._money_flow_field_map(item) for item in raw_items]
        data = {"symbol": symbol, "items": items, "source": best.get("provider") if best else ""}
        coverage = self._build_single_section_coverage(items[-1] if items else {}, "money_flow")
        quality = self._aggregate_quality([{"confidence": "low" if len(self._valid_route_results(route_results)) <= 1 else "medium"}], coverage)
        envelope = self._envelope(
            ok=bool(items),
            data=data,
            coverage=coverage,
            quality=quality,
            sources=self._source_summary(route_results),
            warnings=[],
            errors=self._route_errors(route_results) if not items else [],
        )
        self.cache.set(cache_key, envelope, "money_flow")
        return envelope

    def validate_stock_data(self, symbol: str, fields: list[str], date: str | None = None, period: str | None = None) -> dict:
        symbol = normalize_symbol(symbol)
        validations: list[dict] = []
        warnings: list[str] = []
        errors: list[str] = []
        sources: list[dict] = []

        for field in fields or []:
            provider_values = self._collect_validation_values(symbol, field, date=date, period=period)
            sources.extend(provider_values.get("sources", []))
            errors.extend(provider_values.get("errors", []))
            validation = self.quality_checker.validate_field(field, provider_values.get("values", []))
            validation.symbol = symbol
            validations.append(validation.model_dump())
            warnings.extend(validation.warnings)

        quality = self._quality_from_validations(validations)
        return self._envelope(
            ok=bool(validations),
            data={"symbol": symbol, "validations": validations},
            coverage={
                "requested_fields": len(fields or []),
                "filled_fields": sum(1 for item in validations if item.get("confidence") != "missing"),
                "missing_fields": [item["field"] for item in validations if item.get("confidence") == "missing"],
            },
            quality=quality,
            sources=self._dedupe_sources(sources),
            warnings=self._dedupe_strings(warnings),
            errors=self._dedupe_strings(errors),
        )

    def provider_status(self) -> dict:
        providers = []
        for name, provider in self.router.get_providers("status"):
            cfg = PROVIDER_CONFIG.get(name, {})
            providers.append({
                "provider": name,
                "enabled": cfg.get("enabled", True),
                "priority": cfg.get("priority"),
                "source_family": cfg.get("source_family", name),
                "class": provider.__class__.__name__,
            })
        return {"providers": providers}

    # ------------------------------------------------------------------
    # Merge / validation internals
    # ------------------------------------------------------------------
    def _extract_provider_items(self, route_results: list[dict], symbol: str) -> list[dict]:
        items: list[dict] = []
        for result in route_results:
            rows = result.get("data")
            if result.get("error") or not isinstance(rows, list):
                continue
            for row in rows:
                if normalize_symbol(row.get("symbol", "")) == symbol:
                    items.append({
                        "provider": result["provider"],
                        "source_family": result.get("source_family"),
                        "data": row,
                    })
        return items

    def _extract_single_provider_dicts(self, route_results: list[dict], mapper) -> list[dict]:
        items = []
        for result in route_results:
            row = result.get("data")
            if result.get("error") or not isinstance(row, dict):
                continue
            mapped = mapper(row, result["provider"])
            if mapped:
                items.append({
                    "provider": result["provider"],
                    "source_family": result.get("source_family"),
                    "data": mapped,
                })
        return items

    def _merge_provider_dicts(self, provider_items: list[dict], mapper) -> tuple[dict, list[str]]:
        merged: dict = {}
        used_sources: list[str] = []
        for item in provider_items:
            data = mapper(item["data"], item["provider"])
            if not isinstance(data, dict):
                continue
            source_used = False
            for key, value in data.items():
                if key.startswith("_"):
                    continue
                if key not in merged and _is_filled(value):
                    merged[key] = value
                    source_used = True
            if source_used:
                used_sources.append(item["provider"])
        return merged, self._dedupe_strings(used_sources)

    def _quality_for_provider_items(self, symbol: str, provider_items: list[dict], fields: dict[str, str]) -> dict:
        validations = self._validate_fields_from_provider_items(symbol, provider_items, fields)
        return self._quality_from_validations(validations)

    def _validate_fields_from_provider_items(self, symbol: str, provider_items: list[dict], fields: dict[str, str]) -> list[dict]:
        validations = []
        for data_field, validation_field in fields.items():
            provider_values = []
            for item in provider_items:
                value = _safe_float(item["data"].get(data_field))
                if value is None:
                    continue
                provider_values.append({
                    "provider": item["provider"],
                    "source_family": item.get("source_family"),
                    "data": value,
                })
            validation = self.quality_checker.validate_field(validation_field, provider_values)
            validation.symbol = symbol
            validations.append(validation.model_dump())
        return validations

    def _collect_validation_values(self, symbol: str, field: str, date: str | None = None, period: str | None = None) -> dict:
        source_events = []
        errors = []
        values = []
        if field in {"close", "volume", "open", "high", "low"}:
            results = self.router.route_all(
                "kline",
                "get_kline",
                symbol,
                period or "daily",
                _compact_date(date) or "20200101",
                _compact_date(date) or _compact_date(_now_iso()[:10]) or "20261231",
                "qfq",
                5,
            )
            source_events = self._source_summary(results)
            errors = self._route_errors(results)
            for result in results:
                rows = result.get("data")
                if result.get("error") or not isinstance(rows, list) or not rows:
                    continue
                row = rows[-1]
                value = _safe_float(row.get(field))
                if value is not None:
                    values.append({"provider": result["provider"], "source_family": result.get("source_family"), "data": value})
        elif field in {"pe", "pb", "ps", "dividend_yield"}:
            results = self.router.route_all("valuation", "get_valuation", symbol)
            source_events = self._source_summary(results)
            errors = self._route_errors(results)
            for item in self._extract_single_provider_dicts(results, self._valuation_field_map):
                value = _safe_float(item["data"].get(field))
                if value is not None:
                    values.append({"provider": item["provider"], "source_family": item.get("source_family"), "data": value})
        else:
            results = self.router.route_all("financial", "get_financials", symbol)
            source_events = self._source_summary(results)
            errors = self._route_errors(results)
            for item in self._extract_single_provider_dicts(results, self._financial_field_map):
                value = _safe_float(item["data"].get(field))
                if value is not None:
                    values.append({"provider": item["provider"], "source_family": item.get("source_family"), "data": value})
        return {"values": values, "sources": source_events, "errors": errors}

    # ------------------------------------------------------------------
    # Field mapping
    # ------------------------------------------------------------------
    def _identity_map(self, data: dict, provider: str = "") -> dict:
        return dict(data or {})

    def _quote_field_map(self, data: dict, provider: str = "") -> dict:
        data = dict(data or {})
        return {
            "symbol": normalize_symbol(data.get("symbol", "")),
            "name": data.get("name") or data.get("stock_name"),
            "price": _safe_float(data.get("price")),
            "open": _safe_float(data.get("open")),
            "pre_close": _safe_float(data.get("pre_close")),
            "high": _safe_float(data.get("high")),
            "low": _safe_float(data.get("low")),
            "volume": _safe_float(data.get("volume")),
            "amount": _safe_float(data.get("amount")),
            "change": _safe_float(data.get("change")),
            "pct_change": _safe_float(data.get("pct_change")),
            "turnover_rate": _safe_float(data.get("turnover_rate")),
            "pe": _safe_float(data.get("pe") or data.get("pe_ttm")),
            "pb": _safe_float(data.get("pb")),
            "market_cap": self._normalize_market_cap(data.get("total_mv"), provider),
            "circulating_cap": self._normalize_market_cap(data.get("circ_mv"), provider),
        }

    def _financial_field_map(self, data: dict, provider: str = "") -> dict:
        data = dict(data or {})
        return {
            "symbol": normalize_symbol(data.get("symbol", "")),
            "report_date": data.get("report_date") or data.get("period") or data.get("stat_date") or data.get("pub_date"),
            "revenue": self._normalize_money_to_yi(data.get("revenue") or data.get("MBRevenue"), provider),
            "net_profit": self._normalize_money_to_yi(data.get("net_profit"), provider),
            "revenue_growth": _safe_float(data.get("revenue_growth") or data.get("revenue_yoy") or data.get("or_yoy")),
            "profit_growth": _safe_float(data.get("profit_growth") or data.get("net_profit_yoy") or data.get("q_profit_yoy") or data.get("yoy_net_profit")),
            "gross_margin": _safe_float(data.get("gross_margin")),
            "net_margin": _safe_float(data.get("net_margin")),
            "roe": _safe_float(data.get("roe")),
            "roa": _safe_float(data.get("roa")),
            "debt_ratio": _safe_float(data.get("debt_ratio")),
            "operating_cashflow": self._normalize_money_to_yi(data.get("operating_cashflow") or data.get("ocf_per_share"), provider),
        }

    def _valuation_field_map(self, data: dict, provider: str = "") -> dict:
        data = dict(data or {})
        pe = _safe_float(data.get("pe"))
        pe_ttm = _safe_float(data.get("pe_ttm"))
        return {
            "symbol": normalize_symbol(data.get("symbol", "")),
            "trade_date": data.get("trade_date") or data.get("date"),
            "pe": pe if pe is not None else pe_ttm,
            "pe_ttm": pe_ttm,
            "pb": _safe_float(data.get("pb")),
            "ps": _safe_float(data.get("ps") or data.get("ps_ttm")),
            "dividend_yield": _safe_float(data.get("dividend_yield")),
            "market_cap": self._normalize_market_cap(data.get("market_cap") or data.get("total_mv"), provider),
            "circulating_cap": self._normalize_market_cap(data.get("circulating_cap") or data.get("circ_mv"), provider),
        }

    def _money_flow_field_map(self, data: dict) -> dict:
        return {
            "date": data.get("date"),
            "main_net_inflow": _safe_float(data.get("main_net_inflow") or data.get("net_main")),
            "retail_net_inflow": _safe_float(data.get("retail_net_inflow") or data.get("net_small")),
            "net_inflow_ratio": _safe_float(data.get("net_inflow_ratio") or data.get("net_main_pct")),
            "turnover_rate": _safe_float(data.get("turnover_rate")),
            "north_flow": _safe_float(data.get("north_flow")),
        }

    def _normalize_money_to_yi(self, value: Any, provider: str) -> float | None:
        number = _safe_float(value)
        if number is None:
            return None
        # Tushare / Baostock 常见金额单位是元；非常大的数按元转亿元。
        if abs(number) > 1_000_000:
            return round(number / 100_000_000, 6)
        return number

    def _normalize_market_cap(self, value: Any, provider: str) -> float | None:
        number = _safe_float(value)
        if number is None:
            return None
        if provider == "tushare":
            # Tushare daily_basic total_mv/circ_mv 单位一般为万元。
            return round(number / 10_000, 6)
        if abs(number) > 1_000_000:
            return round(number / 100_000_000, 6)
        return number

    # ------------------------------------------------------------------
    # Coverage / quality / response helpers
    # ------------------------------------------------------------------
    def _build_bundle_coverage(self, symbols_data: dict[str, dict], sections: list[str]) -> dict:
        requested = 0
        filled = 0
        missing: list[str] = []
        for symbol, payload in symbols_data.items():
            for section in sections:
                section_fields = SECTION_FIELDS.get(section, [])
                requested += len(section_fields)
                section_data = payload.get(section, {})
                if isinstance(section_data, list):
                    sample = section_data[-1] if section_data else {}
                else:
                    sample = section_data
                for field in section_fields:
                    if _is_filled(sample.get(field) if isinstance(sample, dict) else None):
                        filled += 1
                    else:
                        missing.append(f"{symbol}.{section}.{field}")
        return {"requested_fields": requested, "filled_fields": filled, "missing_fields": missing}

    def _build_section_coverage(self, data_by_symbol: dict[str, dict], section: str) -> dict:
        requested = 0
        filled = 0
        missing = []
        fields = SECTION_FIELDS.get(section, [])
        for symbol, data in data_by_symbol.items():
            requested += len(fields)
            for field in fields:
                if _is_filled(data.get(field)):
                    filled += 1
                else:
                    missing.append(f"{symbol}.{field}")
        return {"requested_fields": requested, "filled_fields": filled, "missing_fields": missing}

    def _build_single_section_coverage(self, data: dict, section: str) -> dict:
        fields = SECTION_FIELDS.get(section, [])
        missing = [field for field in fields if not _is_filled(data.get(field))]
        return {"requested_fields": len(fields), "filled_fields": len(fields) - len(missing), "missing_fields": missing}

    def _build_bundle_quality(self, symbol_quality: dict[str, dict], coverage: dict) -> dict:
        aggregate = self._aggregate_quality(list(symbol_quality.values()), coverage)
        aggregate["by_symbol"] = symbol_quality
        return aggregate

    def _quality_from_validations(self, validations: list[dict]) -> dict:
        quality = self._empty_quality()
        if not validations:
            quality["confidence"] = "low"
            return quality
        confidences = []
        for item in validations:
            field = item.get("field", "")
            confidence = item.get("confidence", "low")
            confidences.append(confidence)
            if confidence == "conflict":
                quality["conflict_fields"].append(field)
            elif confidence == "low":
                quality["low_confidence_fields"].append(field)
            elif confidence == "missing":
                quality["missing_fields"].append(field)
            if confidence not in {"missing"}:
                quality["validated_fields"].append(field)
            quality["warnings"].extend(item.get("warnings", []))
        quality["confidence"] = self._min_confidence(confidences)
        for key in ("validated_fields", "conflict_fields", "low_confidence_fields", "missing_fields", "warnings"):
            quality[key] = self._dedupe_strings(quality[key])
        return quality

    def _aggregate_quality(self, qualities: list[dict], coverage: dict) -> dict:
        if not qualities:
            qualities = [self._empty_quality()]
        confidence = self._min_confidence([item.get("confidence", "low") for item in qualities])
        conflict_fields = []
        low_confidence_fields = []
        validated_fields = []
        missing_fields = list(coverage.get("missing_fields", []))
        warnings = []
        for item in qualities:
            conflict_fields.extend(item.get("conflict_fields", []))
            low_confidence_fields.extend(item.get("low_confidence_fields", []))
            validated_fields.extend(item.get("validated_fields", []))
            missing_fields.extend(item.get("missing_fields", []))
            warnings.extend(item.get("warnings", []))
        if conflict_fields:
            confidence = "conflict"
        elif coverage.get("requested_fields") and coverage.get("filled_fields", 0) == 0:
            confidence = "missing"
        elif missing_fields and confidence == "high":
            confidence = "medium"
        return {
            "confidence": confidence,
            "validated_fields": self._dedupe_strings(validated_fields),
            "conflict_fields": self._dedupe_strings(conflict_fields),
            "low_confidence_fields": self._dedupe_strings(low_confidence_fields),
            "missing_fields": self._dedupe_strings(missing_fields),
            "warnings": self._dedupe_strings(warnings),
        }

    def _merge_quality(self, target: dict, source: dict) -> None:
        if not source:
            return
        target["confidence"] = self._min_confidence([target.get("confidence", "high"), source.get("confidence", "low")])
        for key in ("validated_fields", "conflict_fields", "low_confidence_fields", "missing_fields", "warnings"):
            target.setdefault(key, [])
            target[key].extend(source.get(key, []))
            target[key] = self._dedupe_strings(target[key])

    def _empty_quality(self) -> dict:
        return {
            "confidence": "high",
            "validated_fields": [],
            "conflict_fields": [],
            "low_confidence_fields": [],
            "missing_fields": [],
            "warnings": [],
        }

    def _min_confidence(self, confidences: list[str]) -> str:
        if not confidences:
            return "low"
        return min(confidences, key=lambda item: QUALITY_ORDER.get(item, 2))

    def _envelope(
        self,
        ok: bool,
        data: Any = None,
        coverage: dict | None = None,
        quality: dict | None = None,
        sources: list[dict] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        quality_by_symbol: dict | None = None,
    ) -> dict:
        payload = {
            "ok": ok,
            "data": data,
            "coverage": coverage or {"requested_fields": 0, "filled_fields": 0, "missing_fields": []},
            "quality": quality or self._empty_quality(),
            "sources": sources or [],
            "warnings": self._dedupe_strings(warnings or []),
            "errors": self._dedupe_strings(errors or []),
            "meta": {"request_id": f"req_{uuid.uuid4().hex[:12]}", "timestamp": _now_iso(), "cache_hit": False},
        }
        if quality_by_symbol is not None:
            payload["quality_by_symbol"] = quality_by_symbol
        return payload

    def _source_summary(self, route_results: list[dict]) -> list[dict]:
        summary = []
        for result in route_results:
            summary.append({
                "provider": result.get("provider"),
                "source_family": result.get("source_family") or PROVIDER_CONFIG.get(result.get("provider"), {}).get("source_family"),
                "status": "error" if result.get("error") else "ok",
                "latency_ms": result.get("latency_ms", 0),
                "error": result.get("error", ""),
            })
        return summary

    def _route_errors(self, route_results: list[dict]) -> list[str]:
        return [f"{r.get('provider')}: {r.get('error')}" for r in route_results if r.get("error")]

    def _valid_route_results(self, route_results: list[dict]) -> list[dict]:
        return [r for r in route_results if not r.get("error") and r.get("data") is not None]

    def _first_valid_route_data(self, route_results: list[dict], expected_type: type) -> dict:
        for result in route_results:
            data = result.get("data")
            if result.get("error") or not isinstance(data, expected_type):
                continue
            if expected_type in (list, dict) and not data:
                continue
            return result
        return {}

    def _dedupe_sources(self, sources: list[dict]) -> list[dict]:
        seen = set()
        output = []
        for item in sources:
            key = (item.get("provider"), item.get("status"), item.get("error"))
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        seen = set()
        output = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output

    def _normalize_symbols(self, symbols: list[str] | str | None) -> list[str]:
        if symbols is None:
            return []
        if isinstance(symbols, str):
            symbols = [symbols]
        return [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]

    def _normalize_sections(self, fields: list[str] | None) -> list[str]:
        if not fields:
            return list(DEFAULT_BUNDLE_FIELDS)
        normalized = []
        aliases = {"kline": "kline_daily", "daily_kline": "kline_daily", "quote_realtime": "quote"}
        for field in fields:
            section = aliases.get(str(field), str(field))
            if section in SECTION_FIELDS and section not in normalized:
                normalized.append(section)
        return normalized or list(DEFAULT_BUNDLE_FIELDS)

    def _cache_key(self, prefix: str, **kwargs) -> str:
        return f"{prefix}:{json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str)}"
