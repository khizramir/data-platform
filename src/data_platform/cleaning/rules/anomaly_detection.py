from typing import Any

from data_platform.cleaning.rules.base import OnAnomaly, Rule, RuleResult

_METHODS = frozenset({"zscore", "iqr", "range"})


class AnomalyDetectionRule(Rule):
    """Detects statistical anomalies in numeric field values."""

    def __init__(
        self,
        name: str,
        field: str,
        method: str,
        on_anomaly: OnAnomaly = OnAnomaly.FLAG,
        mean: float | None = None,
        std: float | None = None,
        threshold: float = 3.0,
        q1: float | None = None,
        q3: float | None = None,
        iqr_multiplier: float = 1.5,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        super().__init__(name, field)
        if method not in _METHODS:
            raise ValueError(f"Unknown method '{method}'. Must be one of {sorted(_METHODS)}")
        self.method = method
        self.on_anomaly = on_anomaly
        self.mean = mean
        self.std = std
        self.threshold = threshold
        self.q1 = q1
        self.q3 = q3
        self.iqr_multiplier = iqr_multiplier
        self.min_value = min_value
        self.max_value = max_value

    @property
    def rule_type(self) -> str:
        return "anomaly_detection"

    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return RuleResult(passed=False, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value,
                              message=f"'{value}' is not numeric")
        is_anomaly, message = self._detect(num)
        if is_anomaly:
            return RuleResult(passed=(self.on_anomaly != OnAnomaly.REJECT),
                              field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value,
                              flagged=True, message=message)
        return RuleResult(passed=True, field=self.field, rule_name=self.name,
                          rule_type=self.rule_type, original_value=value)

    def _detect(self, value: float) -> tuple[bool, str]:
        if self.method == "zscore":
            if self.mean is None or self.std is None or self.std == 0:
                return False, ""
            zscore = abs(value - self.mean) / self.std
            if zscore > self.threshold:
                return True, f"Z-score {zscore:.2f} exceeds threshold {self.threshold}"
            return False, ""
        if self.method == "iqr":
            if self.q1 is None or self.q3 is None:
                return False, ""
            iqr = self.q3 - self.q1
            lower, upper = self.q1 - self.iqr_multiplier * iqr, self.q3 + self.iqr_multiplier * iqr
            if value < lower or value > upper:
                return True, f"Value {value} outside IQR bounds [{lower:.2f}, {upper:.2f}]"
            return False, ""
        if self.method == "range":
            if self.min_value is not None and value < self.min_value:
                return True, f"Value {value} below minimum {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return True, f"Value {value} above maximum {self.max_value}"
            return False, ""
        return False, ""
