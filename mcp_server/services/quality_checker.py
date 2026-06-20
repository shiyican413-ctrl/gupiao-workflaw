"""
Quality Checker —— 多源数据交叉验证，计算最终值与可信度。

设计要点：
    - validate_field 聚合同一字段在多个 provider 上的取值。
    - 按 source_family 分组投票，避免同一数据家族被重复计数（例如 efinance
      与 eastmoney 同属 eastmoney 家族）。
    - 最终值策略：
        * >=3 家族：各家族均值的中位数
        * 2 家族：两家族总和的中位数（等价于两者平均）
        * 1 家族：直接取唯一值
    - 可信度：high（>=3 家族且偏差达标）/ medium（2 家族且达标）/ low（单源）/ conflict（超阈值）。
    - 阈值与字段相关，来自 config.VALIDATION_THRESHOLDS。
"""

import statistics

from ..config import PROVIDER_CONFIG, VALIDATION_THRESHOLDS
from ..schemas import ValidationResult, ValidationSource


class QualityChecker:
    """多源数据验证：对比多个源的数据，计算可信度。"""

    def get_source_family(self, provider_name: str) -> str:
        """返回 provider 所属数据源家族，缺省回退为 provider 名本身。"""
        return PROVIDER_CONFIG.get(provider_name, {}).get("source_family", provider_name)

    def validate_field(self, field: str, provider_results: list) -> ValidationResult:
        """
        验证单个字段的多源数据。

        Args:
            field: 字段名（如 "close", "volume"）。
            provider_results: [{"provider": "akshare", "source_family": "mixed",
                               "data": 8.12, "error": None}, ...]

        Returns:
            ValidationResult，含最终值、可信度、偏差、阈值、来源明细与告警。
        """
        # 过滤出有有效数据的结果
        valid = [
            r for r in provider_results
            if r.get("data") is not None and r.get("error") is None
        ]

        if not valid:
            return ValidationResult(
                symbol="",
                field=field,
                final_value=0,
                confidence="missing",
                status="missing",
                max_deviation=0,
                threshold=0,
                sources=[],
                warnings=["无有效数据源"],
            )

        values = [r["data"] for r in valid]

        # 按 source_family 分组投票
        family_votes: dict = {}  # family -> [value, ...]
        for r in valid:
            family = r.get("source_family") or self.get_source_family(r["provider"])
            family_votes.setdefault(family, []).append(r["data"])

        families = list(family_votes.keys())

        # 计算最终值。按 source_family 先聚合，避免同源数据重复投票。
        if len(families) >= 3:
            family_means = [sum(family_votes[f]) / len(family_votes[f]) for f in families]
            final_value = statistics.median(family_means)
        elif len(families) == 2:
            family_means = [sum(family_votes[f]) / len(family_votes[f]) for f in families]
            final_value = statistics.median(family_means)
        else:
            final_value = values[0]

        # 阈值与最大偏差。close 等价格字段使用绝对偏差，其它字段多使用相对偏差。
        threshold_cfg = VALIDATION_THRESHOLDS.get(field, {"type": "relative", "threshold": 0.05})
        threshold = threshold_cfg.get("threshold", 0.05)
        threshold_type = threshold_cfg.get("type", "relative")
        max_deviation = 0.0
        if len(values) > 1:
            if threshold_type == "absolute":
                max_deviation = max(abs(v - final_value) for v in values)
            elif final_value != 0:
                max_deviation = max(abs(v - final_value) / abs(final_value) for v in values)
            else:
                max_deviation = max(abs(v - final_value) for v in values)

        confidence = self._calc_confidence(len(families), max_deviation, threshold)

        warnings = []
        if len(families) == 1:
            warnings.append(f"字段 {field} 仅 {valid[0]['provider']} 单源数据")
        if confidence == "conflict":
            if threshold_type == "absolute":
                warnings.append(f"字段 {field} 多源偏差 {max_deviation:g} 超过阈值 {threshold:g}")
            else:
                warnings.append(
                    f"字段 {field} 多源偏差 {max_deviation:.2%} 超过阈值 {threshold:.2%}"
                )

        sources = [
            ValidationSource(
                provider=r["provider"],
                source_family=r.get("source_family") or "",
                value=r["data"],
                status="ok",
            )
            for r in valid
        ]

        return ValidationResult(
            symbol="",
            field=field,
            final_value=round(final_value, 6),
            confidence=confidence,
            status="passed" if confidence != "conflict" else "conflict",
            max_deviation=round(max_deviation, 4),
            threshold=threshold,
            sources=sources,
            warnings=warnings,
        )

    def _calc_confidence(self, num_families: int, max_deviation: float, threshold: float) -> str:
        """根据家族数量与偏差判定可信度等级。"""
        if num_families >= 3:
            return "high" if max_deviation <= threshold else "conflict"
        if num_families == 2:
            return "medium" if max_deviation <= threshold else "conflict"
        return "low"
