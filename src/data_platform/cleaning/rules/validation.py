import re
from typing import Any

from data_platform.cleaning.rules.base import OnFail, Rule, RuleResult

_CHECKS = frozenset({"not_null", "regex", "range", "enum", "min_length", "max_length"})


class ValidationRule(Rule):
    """Validates field values against criteria without modifying them."""

    def __init__(
        self,
        name: str,
        field: str,
        check: str,
        on_fail: OnFail = OnFail.REJECT,
        pattern: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        values: list[Any] | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        default: Any = None,
    ) -> None:
        super().__init__(name, field)
        if check not in _CHECKS:
            raise ValueError(f"Unknown check '{check}'. Must be one of {sorted(_CHECKS)}")
        self.check = check
        self.on_fail = on_fail
        self._pattern = re.compile(pattern) if pattern else None
        self.min_value = min_value
        self.max_value = max_value
        self.values = values
        self.min_length = min_length
        self.max_length = max_length
        self.default = default

    @property
    def rule_type(self) -> str:
        return "validation"

    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        passed, message = self._run_check(value)
        transformed: Any = None
        if not passed:
            if self.on_fail == OnFail.NULL:
                transformed = None
                passed = True
            elif self.on_fail == OnFail.DEFAULT:
                transformed = self.default
                passed = True
        return RuleResult(
            passed=passed, field=self.field, rule_name=self.name,
            rule_type=self.rule_type, original_value=value,
            transformed_value=transformed, message=message,
        )

    def _run_check(self, value: Any) -> tuple[bool, str]:
        if self.check == "not_null":
            if value is None or value == "":
                return False, f"Field '{self.field}' is null or empty"
            return True, ""
        if self.check == "regex":
            if self._pattern is None:
                return False, "No pattern defined for regex check"
            if not isinstance(value, str) or not self._pattern.fullmatch(value):
                return False, f"'{value}' does not match pattern '{self._pattern.pattern}'"
            return True, ""
        if self.check == "range":
            try:
                num = float(value)
            except (TypeError, ValueError):
                return False, f"'{value}' is not numeric"
            if self.min_value is not None and num < self.min_value:
                return False, f"{num} is below minimum {self.min_value}"
            if self.max_value is not None and num > self.max_value:
                return False, f"{num} is above maximum {self.max_value}"
            return True, ""
        if self.check == "enum":
            if self.values is None or value not in self.values:
                return False, f"'{value}' not in allowed values {self.values}"
            return True, ""
        if self.check == "min_length":
            s = str(value) if value is not None else ""
            if len(s) < (self.min_length or 0):
                return False, f"Length {len(s)} is below minimum {self.min_length}"
            return True, ""
        if self.check == "max_length":
            s = str(value) if value is not None else ""
            if len(s) > (self.max_length or 0):
                return False, f"Length {len(s)} exceeds maximum {self.max_length}"
            return True, ""
        return False, f"Unknown check '{self.check}'"
