"""Tests for the Box plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.box.plugin import BoxPlugin


def make_folder_response(entries):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"entries": entries, "total_count": len(entries)}
    resp.raise_for_status = MagicMock()
    return resp


def make_events_response(events, next_pos="100"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"entries": events, "next_stream_position": next_pos}
    resp.raise_for_status = MagicMock()
    return resp


def make_user_response(status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


def make_config(entries=None):
    stub = MagicMock()
    stub.get.return_value = make_folder_response(entries or [])
    return {"access_token": "tok", "_session_stub": stub}


SAMPLE_ITEMS = [
    {"id": "file1", "type": "file", "name": "contract.pdf", "size": 51200, "created_at": "2024-01-01T00:00:00Z", "modified_at": "2024-01-02T00:00:00Z", "owned_by": {"id": "u1", "name": "Alice"}, "shared_link": None, "etag": "0"},
    {"id": "folder1", "type": "folder", "name": "Legal", "size": 0, "created_at": "2024-01-01T00:00:00Z", "modified_at": "2024-01-01T00:00:00Z", "owned_by": {"id": "u1", "name": "Alice"}, "shared_link": None, "etag": "1"},
]


@pytest.fixture
def plugin():
    return BoxPlugin()


@pytest.fixture
def connected_plugin(plugin):
    plugin.connect(make_config(SAMPLE_ITEMS))
    return plugin


class TestBoxMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "box"

    def test_schemes(self, plugin):
        assert "box" in plugin.metadata.supported_schemes


class TestBoxValidateConfig:
    def test_missing_raises(self, plugin):
        with pytest.raises(ValueError, match="access_token"):
            plugin.validate_config({})

    def test_valid_passes(self, plugin):
        plugin.validate_config({"access_token": "tok"})


class TestBoxConnection:
    def test_not_connected_initially(self, plugin):
        assert not plugin.is_connected()

    def test_connected_after_connect(self, connected_plugin):
        assert connected_plugin.is_connected()

    def test_disconnected(self, connected_plugin):
        connected_plugin.disconnect()
        assert not connected_plugin.is_connected()

    def test_stream_position_reset(self, connected_plugin):
        connected_plugin._stream_position = "999"
        connected_plugin.disconnect()
        assert connected_plugin._stream_position == "0"

    def test_context_manager(self, plugin):
        with plugin:
            plugin.connect(make_config())
            assert plugin.is_connected()
        assert not plugin.is_connected()


class TestBoxTestConnection:
    def test_valid_returns_true(self, plugin):
        stub = MagicMock()
        stub.get.return_value = make_user_response(200)
        assert plugin.test_connection({"access_token": "tok", "_session_stub": stub}) is True

    def test_invalid_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestBoxFetchData:
    def test_returns_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult
        assert isinstance(connected_plugin.fetch_data(), QueryResult)

    def test_row_count(self, connected_plugin):
        assert connected_plugin.fetch_data().row_count == 2

    def test_columns(self, connected_plugin):
        r = connected_plugin.fetch_data()
        assert "id" in r.columns
        assert "type" in r.columns

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()

    def test_folder_id_in_query(self, connected_plugin):
        assert "12345" in connected_plugin.fetch_data(query="12345").query


class TestBoxFetchIncremental:
    def test_returns_events(self, connected_plugin):
        events = [{"event_id": "e1", "event_type": "UPLOAD", "created_at": "2024-01-01T00:00:00Z", "created_by": {"name": "Alice"}, "source": {"id": "f1", "name": "doc.pdf"}}]
        stub = MagicMock()
        stub.get.return_value = make_events_response(events, "200")
        connected_plugin._session = stub
        r = connected_plugin.fetch_incremental(datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert r.row_count == 1
        assert connected_plugin._stream_position == "200"

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestBoxDiscoverSchema:
    def test_keys(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert "total_items" in s
        assert "subfolders" in s

    def test_subfolder(self, connected_plugin):
        assert "Legal" in [f["name"] for f in connected_plugin.discover_schema()["subfolders"]]

    def test_type_counts(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert s["item_types"].get("file") == 1

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()
