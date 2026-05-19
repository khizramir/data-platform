"""Tests for the OneDrive plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.onedrive.plugin import OneDrivePlugin


def make_session_stub(items=None, status=200):
    """Build Graph API session stub."""
    stub = MagicMock()
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"value": items or [], "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/drive/root/delta(token='tok123')"}
    resp.raise_for_status = MagicMock()
    stub.get.return_value = resp
    return stub


def make_config(items=None):
    """Build test config with session stub."""
    return {"access_token": "tok", "_session_stub": make_session_stub(items)}


SAMPLE_ITEMS = [
    {"id": "item1", "name": "budget.xlsx", "size": 2048, "createdDateTime": "2024-01-01T00:00:00Z", "lastModifiedDateTime": "2024-01-02T00:00:00Z", "webUrl": "https://onedrive.live.com/item1", "file": {"mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}},
    {"id": "folder1", "name": "Reports", "size": None, "createdDateTime": "2024-01-01T00:00:00Z", "lastModifiedDateTime": "2024-01-01T00:00:00Z", "webUrl": "https://onedrive.live.com/folder1", "folder": {"childCount": 5}},
]


@pytest.fixture
def plugin():
    return OneDrivePlugin()


@pytest.fixture
def connected_plugin(plugin):
    plugin.connect(make_config(SAMPLE_ITEMS))
    return plugin


class TestOneDriveMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "onedrive"

    def test_schemes(self, plugin):
        assert "onedrive" in plugin.metadata.supported_schemes


class TestOneDriveValidateConfig:
    def test_missing_raises(self, plugin):
        with pytest.raises(ValueError, match="access_token"):
            plugin.validate_config({})

    def test_valid_passes(self, plugin):
        plugin.validate_config({"access_token": "tok"})


class TestOneDriveConnection:
    def test_not_connected_initially(self, plugin):
        assert not plugin.is_connected()

    def test_connected_after_connect(self, connected_plugin):
        assert connected_plugin.is_connected()

    def test_disconnected_after_disconnect(self, connected_plugin):
        connected_plugin.disconnect()
        assert not connected_plugin.is_connected()

    def test_delta_cleared_on_disconnect(self, connected_plugin):
        connected_plugin._delta_token = "tok"
        connected_plugin.disconnect()
        assert connected_plugin._delta_token is None

    def test_context_manager(self, plugin):
        with plugin:
            plugin.connect(make_config())
            assert plugin.is_connected()
        assert not plugin.is_connected()


class TestOneDriveTestConnection:
    def test_valid_returns_true(self, plugin):
        assert plugin.test_connection(make_config()) is True

    def test_invalid_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestOneDriveFetchData:
    def test_returns_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult
        assert isinstance(connected_plugin.fetch_data(), QueryResult)

    def test_row_count(self, connected_plugin):
        assert connected_plugin.fetch_data().row_count == 2

    def test_columns(self, connected_plugin):
        r = connected_plugin.fetch_data()
        assert "id" in r.columns
        assert "is_folder" in r.columns

    def test_delta_token_stored(self, connected_plugin):
        connected_plugin.fetch_data()
        assert connected_plugin._delta_token == "tok123"

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()

    def test_folder_flagged(self, connected_plugin):
        r = connected_plugin.fetch_data()
        col = r.columns.index("is_folder")
        flags = [row[col] for row in r.rows]
        assert True in flags
        assert False in flags


class TestOneDriveFetchIncremental:
    def test_no_token_does_full_fetch(self, connected_plugin):
        connected_plugin._delta_token = None
        assert connected_plugin.fetch_data().row_count == 2

    def test_with_token_uses_delta(self, connected_plugin):
        connected_plugin._delta_token = "existing"
        r = connected_plugin.fetch_incremental(datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert "delta" in r.query

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestOneDriveDiscoverSchema:
    def test_keys(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert "total_items" in s
        assert "subfolders" in s

    def test_subfolder(self, connected_plugin):
        assert "Reports" in [f["name"] for f in connected_plugin.discover_schema()["subfolders"]]

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()
