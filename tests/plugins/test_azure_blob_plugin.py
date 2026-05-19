"""Tests for the Azure Blob Storage plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.azure_blob.plugin import AzureBlobPlugin


def make_blob_item(name, size=1024, last_modified=None, content_type="application/octet-stream"):
    blob = MagicMock()
    blob.name = name
    blob.size = size
    blob.last_modified = last_modified or datetime(2024, 1, 2, tzinfo=timezone.utc)
    blob.content_settings = MagicMock()
    blob.content_settings.content_type = content_type
    blob.etag = '"etag_abc"'
    blob.blob_type = "BlockBlob"
    blob.lease = MagicMock()
    blob.lease.status = "unlocked"
    return blob


def make_client_stub(blobs=None):
    stub = MagicMock()
    stub.list_blobs.return_value = iter(blobs or [])
    stub.exists.return_value = True
    return stub


def make_config(blobs=None):
    return {"container_name": "my-container", "connection_string": "DefaultEndpointsProtocol=https;...", "_client_stub": make_client_stub(blobs)}


SAMPLE_BLOBS = [
    make_blob_item("data/sales.csv", size=10240, content_type="text/csv", last_modified=datetime(2024, 1, 2, tzinfo=timezone.utc)),
    make_blob_item("data/archive/old.parquet", size=204800, content_type="application/octet-stream", last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc)),
]


@pytest.fixture
def plugin():
    return AzureBlobPlugin()


@pytest.fixture
def connected_plugin(plugin):
    plugin.connect(make_config(SAMPLE_BLOBS))
    return plugin


class TestAzureBlobMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "azure_blob"

    def test_schemes(self, plugin):
        assert "abfs" in plugin.metadata.supported_schemes


class TestAzureBlobValidateConfig:
    def test_missing_container_raises(self, plugin):
        with pytest.raises(ValueError, match="container_name"):
            plugin.validate_config({})

    def test_missing_creds_raises(self, plugin):
        with pytest.raises(ValueError, match="connection_string"):
            plugin.validate_config({"container_name": "c"})

    def test_conn_str_passes(self, plugin):
        plugin.validate_config({"container_name": "c", "connection_string": "..."})

    def test_account_key_passes(self, plugin):
        plugin.validate_config({"container_name": "c", "account_name": "a", "account_key": "k"})

    def test_sas_passes(self, plugin):
        plugin.validate_config({"container_name": "c", "account_name": "a", "sas_token": "?s=x"})


class TestAzureBlobConnection:
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


class TestAzureBlobTestConnection:
    def test_valid_returns_true(self, plugin):
        assert plugin.test_connection(make_config()) is True

    def test_invalid_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestAzureBlobFetchData:
    def test_returns_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult
        assert isinstance(connected_plugin.fetch_data(), QueryResult)

    def test_row_count(self, connected_plugin):
        assert connected_plugin.fetch_data().row_count == 2

    def test_azure_uri(self, connected_plugin):
        assert connected_plugin.fetch_data().query.startswith("azure://")

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()


class TestAzureBlobFetchIncremental:
    def test_filters_by_timestamp(self):
        plugin = AzureBlobPlugin()
        plugin.connect(make_config(SAMPLE_BLOBS))
        r = plugin.fetch_incremental(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        assert r.row_count == 1
        assert r.rows[0][r.columns.index("name")] == "data/sales.csv"

    def test_future_cutoff_excludes_all(self, connected_plugin):
        assert connected_plugin.fetch_incremental(datetime(2025, 1, 1, tzinfo=timezone.utc)).row_count == 0

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestAzureBlobDiscoverSchema:
    def test_keys(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert "total_blobs" in s
        assert "virtual_dirs" in s

    def test_virtual_dirs(self, connected_plugin):
        assert any("data" in d for d in connected_plugin.discover_schema()["virtual_dirs"])

    def test_content_types(self, connected_plugin):
        assert "text/csv" in connected_plugin.discover_schema()["content_types"]

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()
