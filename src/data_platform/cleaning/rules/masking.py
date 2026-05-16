import hashlib
from typing import Any

from data_platform.cleaning.rules.base import Rule, RuleResult

_STRATEGIES = frozenset({"full", "partial", "email", "hash"})


class MaskingRule(Rule):
    """Masks sensitive field values to protect PII."""

    def __init__(
        self,
        name: str,
        field: str,
        strategy: str,
        visible_chars: int = 4,
        mask_char: str = "*",
        position: str = "end",
    ) -> None:
        super().__init__(name, field)
        if strategy not in _STRATEGIES:
            raise ValueError(f"Unknown masking strategy '{strategy}'. Must be one of {sorted(_STRATEGIES)}")
        if position not in ("start", "end"):
            raise ValueError("position must be 'start' or 'end'")
        self.strategy = strategy
        self.visible_chars = visible_chars
        self.mask_char = mask_char
        self.position = position

    @property
    def rule_type(self) -> str:
        return "masking"

    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        if value is None:
            return RuleResult(passed=True, field=self.field, rule_name=self.name,
                              rule_type=self.rule_type, original_value=value)
        return RuleResult(passed=True, field=self.field, rule_name=self.name,
                          rule_type=self.rule_type, original_value=value, transformed_value=self._mask(str(value)))

    def _mask(self, value: str) -> str:
        if self.strategy == "full":
            return self.mask_char * len(value)
        if self.strategy == "partial":
            n = min(self.visible_chars, len(value))
            mask_count = len(value) - n
            if self.position == "end":
                return self.mask_char * mask_count + value[-n:] if n else self.mask_char * len(value)
            return value[:n] + self.mask_char * mask_count
        if self.strategy == "email":
            if "@" not in value:
                return self.mask_char * len(value)
            local, domain = value.split("@", 1)
            if len(local) <= 2:
                masked_local = self.mask_char * len(local)
            else:
                masked_local = local[0] + self.mask_char * (len(local) - 2) + local[-1]
            return f"{masked_local}@{domain}"
        if self.strategy == "hash":
            return hashlib.sha256(value.encode()).hexdigest()[:16]
        return value
