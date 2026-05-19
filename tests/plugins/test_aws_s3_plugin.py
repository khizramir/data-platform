"""Tests for the AWS S3 plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.aws_s3.plugin import AWSS3Plugin


def make_paginator_stub(objects):
    paginator = MagicMock()
    paginator.paginate.side_effect = lambda **_kwargs: iter([{"Contents": objects, "CommonPrefixes": []}])
    return paginator


def make_client_stub(objects=None):
    client = MagicMock()
    client.get_paginator.return_value = make_paginator_stub(objects or [])
    client.head_bucket.return_value = {}
    return client


def make_config(objects=None):
    return {"bucket": "my-bucket", "_client_stub": make_client_stub(objects)}


def make_dt(year=2024, month=1, day=2):
    return datetime(year, month, day, tzinfo=timezone.utc)


SAMPLE_OBJECTS = [
    {"Key": "data/sales.csv", "Size": 10240, "LastModified": make_dt(2024, 1, 2), "ETag": '"abc"', "StorageClass": "STANDARD", "Owner": {"DisplayName": "alice", "ID": "u1"}},
    {"Key": "data/logs.json", "Size": 2048, "LastModified": make_dt(2024, 1, 1), "ETag": '"def"', "StorageClass": "STANDARD", "Owner": {"DisplayName": "alice", "ID": "u1"}},
]


@pytest.fixture
def plugin():
    return AWSS3Plugin()


@pytest.fixture
def connected_plugin(plugin):
    plugin.connect(make_config(SAMPLE_OBJECTS))
    return plugin


class TestAWSS3Metadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "aws_s3"

    def test_schemes(self, plugin):
        assert "s3" in plugin.metadata.supported_schemes


class TestAWSS3ValidateConfig:
    def test_missing_raises(self, plugin):
        with pytest.raises(ValueError, match="bucket"):
            plugin.validate_config({})

    def test_valid_passes(self, plugin):
        plugin.validate_config({"bucket": "b"})


class TestAWSS3Connection:
    def test_not_connected_initially(self, plugin):
        assert not plugin.is_connected()

    def test_connected_after_connect(self, connected_plugin):
        assert connected_plugin.is_connected()

    def test_disconnected(self, connected_plugin):
        connected_plugin.disconnect()
        assert not connected_plugin.is_connected()

    def test_context_manager(self, plugin):
        with plugin:
            plugin.connect(make_config())
            assert plugin.is_connected()
        assert not plugin.is_connected()


class TestAWSS3TestConnection:
    def test_valid_returns_true(self, plugin):
        assert plugin.test_connection(make_config()) is True

    def test_invalid_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestAWSS3FetchData:
    def test_returns_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult
        assert isinstance(connected_plugin.fetch_data(), QueryResult)

    def test_row_count(self, connected_plugin):
        assert connected_plugin.fetch_data().row_count == 2

    def test_s3_uri_in_query(self, connected_plugin):
        assert connected_plugin.fetch_data().query.startswith("s3://")

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()


class TestAWSS3FetchIncremental:
    def test_filters_by_timestamp(self, connected_plugin):
        r = connected_plugin.fetch_incremental(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        assert r.row_count == 1
        assert r.rows[0][r.columns.index("Key")] == "data/sales.csv"

    def test_all_excluded_future_cutoff(self, connected_plugin):
        assert connected_plugin.fetch_incremental(datetime(2025, 1, 1, tzinfo=timezone.utc)).row_count == 0

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestAWSS3DiscoverSchema:
    def test_keys(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert "total_objects" in s
        assert "extensions" in s

    def test_extensions(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert "csv" in s["extensions"]
        assert "json" in s["extensions"]

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()
