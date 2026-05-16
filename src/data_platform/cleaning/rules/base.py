from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OnFail(str, Enum):
    REJECT = "reject"
    WARN = "warn"
    NULL = "null"
    DEFAULT = "default"


class OnAnomaly(str, Enum):
    FLAG = "flag"
    REJECT = "reject"
    WARN = "warn"


@dataclass
class RuleResult:
    passed: bool
    field: str
    rule_name: str
    rule_type: str
    original_value: Any
    transformed_value: Any = None
    message: str = ""
    flagged: bool = False

    @property
    def effective_value(self) -> Any:
        return self.transformed_value if self.transformed_value is not None else self.original_value


class Rule(ABC):
    """Abstract base class for all data cleaning rules."""

    def __init__(self, name: str, field: str) -> None:
        self.name = name
        self.field = field

    @abstractmethod
    def apply(self, value: Any, record: dict[str, Any]) -> RuleResult:
        """Apply the rule to *value* in context of the full *record*."""

    @property
    @abstractmethod
    def rule_type(self) -> str:
        """Return the rule type string identifier."""
