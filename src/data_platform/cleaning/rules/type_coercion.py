from datetime import datetime
from typing import Any

from data_platform.cleaning.rules.base import OnFail, Rule, RuleResult

_TARGET_TYPES = frozenset({"int", "float", "str", "bool", "datetime"})
_DEFAULT_TRUE  = frozenset({"true", "yes", "1", "on"})
_DEFAULT_FALSE = frozenset({"false", "no", "0", "off"})


class TypeCoercionRule(Rule):
    """Coerces field values to a target Python type."""

    def __init__(
        self,
        name: str,
        field: str,
        target_type: str,
        on_fail: OnFail = OnFail.REJECT,
        datetime_format: str = "%Y-%m-%d",
        default: Any = None,
        true_values: list[str] | None = None,
        false_values: list[str] | None = None,
    ) -> None:
        super().__init__(name, field)
        if target_type not in _TARGET_TYPES:
            raise ValueError(f"Unknown target type '{target_type}'. Must be one of {sorted(_TARGET_TYPES)}")
        self.target_type = target_type
        self.on_fail = on_fail
        self.datetime_format = datetime_format
        self.default = default
        self._true  = frozenset(v.lower() for v in (true_values  or [])) or _DEFAULT_TRUE
        self._false = frozenset(v.lower() for v in (false_values or [])) or _DEFAULT_FALSE

    @property
    def rule_type(self) -> str:
        return "type_coercion"

    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        if value is None:
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, transformed_value=None)
        try:
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, transformed_value=self._coerce(value))
        except (ValueError, TypeError) as exc:
            if self.on_fail == OnFail.NULL:
                return RuleResult(passed=True, field=self.field, rule_name=self.name,
                                  rule_type=self.rule_type, original_value=value, transformed_value=None)
            if self.on_fail == OnFail.DEFAULT:
                return RuleResult(passed=True, field=self.field, rule_name=self.name,
                                  rule_type=self.rule_type, original_value=value, transformed_value=self.default)
            return RuleResult(passed=False, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, message=str(exc))

    def _coerce(self, value: Any) -> Any:
        if self.target_type == "int":      return int(float(str(value)))
        if self.target_type == "float":    return float(str(value))
        if self.target_type == "str":      return str(value)
        if self.target_type == "bool":
            s = str(value).lower()
            if s in self._true:  return True
            if s in self._false: return False
            raise ValueError(f"Cannot coerce '{value}' to bool")
        if self.target_type == "datetime":
            if isinstance(value, datetime): return value
            return datetime.strptime(str(value), self.datetime_format)
        raise ValueError(f"Unknown target type '{self.target_type}'")
