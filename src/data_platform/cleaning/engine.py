from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from data_platform.cleaning.loader import load_rules_from_dict, load_rules_from_yaml
from data_platform.cleaning.rules.base import Rule, RuleResult


@dataclass
class RecordResult:
    """Result of running the cleaning engine over a single record."""
    original: dict[str, Any]
    cleaned: dict[str, Any]
    rule_results: list[RuleResult]
    passed: bool
    rejected: bool

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.rule_results if not r.passed]

    @property
    def anomalies(self) -> list[RuleResult]:
        return [r for r in self.rule_results if r.flagged]


class CleaningEngine:
    """Processes records through an ordered pipeline of cleaning rules."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    def add_rules(self, rules: list[Rule]) -> None:
        self._rules.extend(rules)

    def load_rules_from_yaml(self, path: str | Path) -> None:
        self._rules.extend(load_rules_from_yaml(path))

    def load_rules_from_dict(self, data: dict[str, Any]) -> None:
        self._rules.extend(load_rules_from_dict(data))

    def process_record(self, record: dict[str, Any]) -> RecordResult:
        cleaned = dict(record)
        results: list[RuleResult] = []
        rejected = False
        for rule in self._rules:
            result = rule.apply(cleaned.get(rule.field), cleaned)
            results.append(result)
            if result.transformed_value is not None:
                cleaned[rule.field] = result.transformed_value
            if not result.passed:
                rejected = True
        return RecordResult(original=record, cleaned=cleaned,
                            rule_results=results, passed=not rejected, rejected=rejected)

    def process_stream(self, records: Iterable[dict[str, Any]]) -> Iterator[RecordResult]:
        for record in records:
            yield self.process_record(record)
