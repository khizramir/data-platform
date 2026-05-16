from pathlib import Path
from typing import Any

import yaml

from data_platform.cleaning.rules.anomaly_detection import AnomalyDetectionRule
from data_platform.cleaning.rules.base import OnAnomaly, OnFail, Rule
from data_platform.cleaning.rules.masking import MaskingRule
from data_platform.cleaning.rules.standardization import StandardizationRule
from data_platform.cleaning.rules.transformation import TransformationRule
from data_platform.cleaning.rules.type_coercion import TypeCoercionRule
from data_platform.cleaning.rules.validation import ValidationRule

_RULE_CLASSES: dict[str, type[Rule]] = {
    "validation": ValidationRule,
    "transformation": TransformationRule,
    "standardization": StandardizationRule,
    "type_coercion": TypeCoercionRule,
    "masking": MaskingRule,
    "anomaly_detection": AnomalyDetectionRule,
}


class RuleLoaderError(Exception):
    pass


def _build_rule(spec: dict[str, Any]) -> Rule:
    rule_type = spec.get("type")
    if rule_type not in _RULE_CLASSES:
        raise RuleLoaderError(f"Unknown rule type '{rule_type}'. Must be one of {sorted(_RULE_CLASSES)}")
    name = spec.get("name")
    field = spec.get("field")
    if not name:
        raise RuleLoaderError("Rule spec is missing required key 'name'")
    if not field:
        raise RuleLoaderError(f"Rule '{name}' is missing required key 'field'")
    kwargs: dict[str, Any] = {k: v for k, v in spec.items() if k not in ("type", "name", "field")}
    if "on_fail" in kwargs:
        kwargs["on_fail"] = OnFail(kwargs["on_fail"])
    if "on_anomaly" in kwargs:
        kwargs["on_anomaly"] = OnAnomaly(kwargs["on_anomaly"])
    try:
        return _RULE_CLASSES[rule_type](name=name, field=field, **kwargs)
    except Exception as exc:
        raise RuleLoaderError(f"Failed to build rule '{name}': {exc}") from exc


def load_rules_from_dict(data: dict[str, Any]) -> list[Rule]:
    """Build Rule objects from an already-parsed dict."""
    if "rules" not in data:
        raise RuleLoaderError("Expected a top-level 'rules' key")
    specs = data["rules"]
    if not isinstance(specs, list):
        raise RuleLoaderError("'rules' must be a list")
    return [_build_rule(spec) for spec in specs]


def load_rules_from_yaml(path: str | Path) -> list[Rule]:
    """Load Rule objects from a YAML file on disk."""
    p = Path(path)
    if not p.exists():
        raise RuleLoaderError(f"Rules file not found: {p}")
    with p.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise RuleLoaderError("YAML must contain a mapping at the top level")
    return load_rules_from_dict(data)
