"""Tests for the Dropbox plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.dropbox.plugin import DropboxPlugin


def make_session_stub(entries: list[dict] | None = None) -> MagicMock:
    """Build a minimal Dropbox API session stub."""
    stub = MagicMock()
    entries = entries or []
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"entries": entries, "cursor": "cur_abc123", "has_more": False}
    response.raise_for_status = MagicMock()
    stub.post.return_value = response
    return stub


def make_config(entries: list[dict] | None = None) -> dict:
    """Build a test config with a session stub."""
    return {"access_token": "tok", "_session_stub": make_session_stub(entries)}


SAMPLE_ENTRIES = [
    {
        ".tag": "file", "id": "id:file1", "name": "report.xlsx",
        "path_display": "/report.xlsx", "size": 4096,
        "client_modified": "2024-01-01T00:00:00Z",
        "server_modified": "2024-01-02T00:00:00Z",
        "content_hash": "abc",
    },
    {
        ".tag": "folder", "id": "id:folder1", "name": "Archive",
        "path_display": "/Archive", "size": None,
        "client_modified": None, "server_modified": None, "content_hash": None,
    },
]


@pytest.fixture
def plugin() -> DropboxPlugin:
    return DropboxPlugin()


@pytest.fixture
def connected_plugin(plugin: DropboxPlugin) -> DropboxPlugin:
    plugin.connect(make_config(SAMPLE_ENTRIES))
    return plugin


class TestDropboxMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "dropbox"

    def test_supported_schemes(self, plugin):
        assert "dropbox" in plugin.metadata.supported_schemes


class TestDropboxValidateConfig:
    def test_missing_token_raises(self, plugin):
        with pytest.raises(ValueError, match="access_token"):
            plugin.validate_config({})

    def test_valid_token_passes(self, plugin):
        plugin.validate_config({"access_token": "tok"})


class TestDropboxConnection:
    def test_not_connected_initially(self, plugin):
        assert not plugin.is_connected()

    def test_connected_after_connect(self, connected_plugin):
        assert connected_plugin.is_connected()

    def test_not_connected_after_disconnect(self, connected_plugin):
        connected_plugin.disconnect()
        assert not connected_plugin.is_connected()

    def test_cursor_cleared_on_disconnect(self, connected_plugin):
        connected_plugin._cursor = "some_cursor"
        connected_plugin.disconnect()
        assert connected_plugin._cursor is None

    def test_context_manager(self, plugin):
        with plugin:
            plugin.connect(make_config())
            assert plugin.is_connected()
        assert not plugin.is_connected()


class TestDropboxTestConnection:
    def test_valid_config_returns_true(self, plugin):
        assert plugin.test_connection(make_config()) is True

    def test_missing_token_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestDropboxFetchData:
    def test_returns_query_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult
        result = connected_plugin.fetch_data()
        assert isinstance(result, QueryResult)

    def test_row_count(self, connected_plugin):
        result = connected_plugin.fetch_data()
        assert result.row_count == 2

    def test_columns_include_tag_and_name(self, connected_plugin):
        result = connected_plugin.fetch_data()
        assert ".tag" in result.columns
        assert "name" in result.columns

    def test_cursor_stored_after_fetch(self, connected_plugin):
        connected_plugin.fetch_data()
        assert connected_plugin._cursor == "cur_abc123"

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()

    def test_rows_contain_file_and_folder(self, connected_plugin):
        result = connected_plugin.fetch_data()
        tag_col = result.columns.index(".tag")
        tags = [row[tag_col] for row in result.rows]
        assert "file" in tags
        assert "folder" in tags


class TestDropboxFetchIncremental:
    def test_without_cursor_does_full_fetch(self, connected_plugin):
        connected_plugin._cursor = None
        result = connected_plugin.fetch_data()
        assert result.row_count == 2

    def test_with_cursor_uses_continue_endpoint(self, connected_plugin):
        connected_plugin._cursor = "existing_cursor"
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        connected_plugin.fetch_incremental(since)
        call_urls = [str(call[0][0]) for call in connected_plugin._session.post.call_args_list]
        assert any("continue" in url for url in call_urls)

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestDropboxDiscoverSchema:
    def test_returns_dict_with_keys(self, connected_plugin):
        schema = connected_plugin.discover_schema()
        assert "total_entries" in schema
        assert "subfolders" in schema
        assert "file_extensions" in schema

    def test_subfolders_listed(self, connected_plugin):
        schema = connected_plugin.discover_schema()
        names = [f["name"] for f in schema["subfolders"]]
        assert "Archive" in names

    def test_file_extension_counted(self, connected_plugin):
        schema = connected_plugin.discover_schema()
        assert "xlsx" in schema["file_extensions"]

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()
