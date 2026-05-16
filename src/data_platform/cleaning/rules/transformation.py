from typing import Any

from data_platform.cleaning.rules.base import Rule, RuleResult

_TRANSFORMS = frozenset({"strip", "lower", "upper", "replace", "prefix", "suffix", "trim_length"})


class TransformationRule(Rule):
    """Applies string transformations to field values."""

    def __init__(
        self,
        name: str,
        field: str,
        transform: str,
        old: str | None = None,
        new: str | None = None,
        prefix: str = "",
        suffix: str = "",
        max_length: int | None = None,
    ) -> None:
        super().__init__(name, field)
        if transform not in _TRANSFORMS:
            raise ValueError(f"Unknown transform '{transform}'. Must be one of {sorted(_TRANSFORMS)}")
        self.transform = transform
        self.old = old
        self.new = new
        self.prefix = prefix
        self.suffix = suffix
        self.max_length = max_length

    @property
    def rule_type(self) -> str:
        return "transformation"

    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        if value is None:
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value)
        try:
            transformed = self._apply_transform(str(value))
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, transformed_value=transformed)
        except Exception as exc:
            return RuleResult(passed=False, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value, message=str(exc))

    def _apply_transform(self, s: str) -> str:
        if self.transform == "strip":       return s.strip()
        if self.transform == "lower":       return s.lower()
        if self.transform == "upper":       return s.upper()
        if self.transform == "replace":     return s.replace(self.old or "", self.new or "")
        if self.transform == "prefix":      return f"{self.prefix}{s}"
        if self.transform == "suffix":      return f"{s}{self.suffix}"
        if self.transform == "trim_length": return s[:self.max_length] if self.max_length is not None else s
        raise ValueError(f"Unknown transform '{self.transform}'")
