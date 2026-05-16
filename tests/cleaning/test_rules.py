import pytest
from datetime import datetime

from data_platform.cleaning.rules.validation import ValidationRule
from data_platform.cleaning.rules.transformation import TransformationRule
from data_platform.cleaning.rules.standardization import StandardizationRule
from data_platform.cleaning.rules.type_coercion import TypeCoercionRule
from data_platform.cleaning.rules.masking import MaskingRule
from data_platform.cleaning.rules.anomaly_detection import AnomalyDetectionRule


def test_validation_not_null_passes():
    r = ValidationRule(name="notnull", field="a", check="not_null")
    res = r.apply("x", {})
    assert res.passed


def test_validation_regex_fails():
    r = ValidationRule(name="re", field="a", check="regex", pattern=r"^\d+$")
    res = r.apply("abc", {})
    assert not res.passed


def test_transformation_strip_and_lower():
    r = TransformationRule(name="t", field="a", transform="strip")
    res = r.apply("  hi  ", {})
    assert res.transformed_value == "hi"
    r2 = TransformationRule(name="t2", field="a", transform="lower")
    assert r2.apply("HELLO", {}).transformed_value == "hello"


def test_standardize_phone_and_date():
    r = StandardizationRule(name="p", field="phone", format="phone_us")
    assert r.apply("+1 (555) 123-4567", {}).transformed_value == "(555) 123-4567"
    r2 = StandardizationRule(name="d", field="date", format="date_iso")
    assert r2.apply("12/31/2020", {}).transformed_value == "2020-12-31"


def test_type_coercion_int_bool_datetime():
    r = TypeCoercionRule(name="c", field="n", target_type="int")
    assert r.apply("3.0", {}).transformed_value == 3
    rb = TypeCoercionRule(name="b", field="f", target_type="bool")
    assert rb.apply("yes", {}).transformed_value is True
    rd = TypeCoercionRule(name="dt", field="t", target_type="datetime", datetime_format="%Y-%m-%d")
    assert rd.apply("2021-01-01", {}).transformed_value == datetime(2021, 1, 1)


def test_masking_strategies():
    r = MaskingRule(name="m", field="e", strategy="email")
    assert "@" in r.apply("alice@example.com", {}).transformed_value
    r2 = MaskingRule(name="h", field="s", strategy="hash")
    assert len(r2.apply("secret", {}).transformed_value) == 16


def test_anomaly_zscore_and_range():
    rz = AnomalyDetectionRule(name="a", field="x", method="zscore", mean=0, std=1, threshold=2)
    res = rz.apply(5, {})
    assert res.flagged
    rr = AnomalyDetectionRule(name="b", field="x", method="range", min_value=0, max_value=10)
    assert not rr.apply(5, {}).flagged
