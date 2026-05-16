import re
from datetime import datetime
from typing import Any

from data_platform.cleaning.rules.base import Rule, RuleResult

_FORMATS = frozenset({"phone_us", "date_iso", "email", "postal_code_us", "name_titlecase"})
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m-%d-%Y", "%d/%m/%Y", "%m/%d/%y")


class StandardizationRule(Rule):
    """Standardizes field values to canonical formats."""

    def __init__(self, name: str, field: str, format: str) -> None:
        super().__init__(name, field)
        if format not in _FORMATS:
            raise ValueError(f"Unknown format '{format}'. Must be one of {sorted(_FORMATS)}")
        self.format = format

    @property
    def rule_type(self) -> str:
        return "standardization"

    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        if value is None:
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value)
        try:
            standardized = self._standardize(str(value))
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, transformed_value=standardized)
        except ValueError as exc:
            return RuleResult(passed=False, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, message=str(exc))

    def _standardize(self, value: str) -> str:
        if self.format == "phone_us":
            digits = re.sub(r"\D", "", value)
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if len(digits) != 10:
                raise ValueError(f"Cannot standardize '{value}' as a US phone number")
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if self.format == "date_iso":
            for fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse '{value}' as a recognizable date")
        if self.format == "email":
            return value.strip().lower()
        if self.format == "postal_code_us":
            digits = re.sub(r"\D", "", value)
            if len(digits) == 5:   return digits
            if len(digits) == 9:   return f"{digits[:5]}-{digits[5:]}"
            raise ValueError(f"Cannot standardize '{value}' as a US postal code")
        if self.format == "name_titlecase":
            return value.strip().title()
        raise ValueError(f"Unknown format '{self.format}'")
