"""Tests for the Google Drive plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.google_drive.plugin import GoogleDrivePlugin


def make_service_stub(files: list[dict] | None = None) -> MagicMock:
    """Build a minimal Drive API service stub."""
    stub = MagicMock()
    files = files or []
    response = {"files": files, "nextPageToken": None}
    stub.files.return_value.list.return_value.execute.return_value = response
    stub.about.return_value.get.return_value.execute.return_value = {"user": {"displayName": "test"}}
    return stub


def make_config(files: list[dict] | None = None) -> dict:
    """Build a test config with a service stub."""
    return {"access_token": "tok", "_service_stub": make_service_stub(files)}


SAMPLE_FILES = [
    {
        "id": "file1", "name": "report.pdf",
        "mimeType": "application/pdf", "size": 1024,
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-02T00:00:00Z",
        "parents": ["root"], "owners": [{"displayName": "Alice"}],
        "shared": False, "webViewLink": "https://drive.google.com/file1",
    },
    {
        "id": "folder1", "name": "Archive",
        "mimeType": "application/vnd.google-apps.folder", "size": None,
        "createdTime": "2024-01-01T00:00:00Z",
        "modifiedTime": "2024-01-01T00:00:00Z",
        "parents": ["root"], "owners": [], "shared": False, "webViewLink": None,
    },
]


@pytest.fixture
def plugin() -> GoogleDrivePlugin:
    return GoogleDrivePlugin()


@pytest.fixture
def connected_plugin(plugin: GoogleDrivePlugin) -> GoogleDrivePlugin:
    plugin.connect(make_config(SAMPLE_FILES))
    return plugin


class TestGoogleDriveMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "google_drive"

    def test_supported_schemes(self, plugin):
        assert "gdrive" in plugin.metadata.supported_schemes


class TestGoogleDriveValidateConfig:
    def test_missing_credentials_raises(self, plugin):
        with pytest.raises(ValueError, match="credentials_file.*access_token"):
            plugin.validate_config({})

    def test_access_token_passes(self, plugin):
        plugin.validate_config({"access_token": "tok"})

    def test_credentials_file_passes(self, plugin):
        plugin.validate_config({"credentials_file": "/path/to/creds.json"})


class TestGoogleDriveConnection:
    def test_not_connected_initially(self, plugin):
        assert not plugin.is_connected()

    def test_connected_after_connect(self, connected_plugin):
        assert connected_plugin.is_connected()

    def test_not_connected_after_disconnect(self, connected_plugin):
        connected_plugin.disconnect()
        assert not connected_plugin.is_connected()

    def test_context_manager(self, plugin):
        with plugin:
            plugin.connect(make_config())
            assert plugin.is_connected()
        assert not plugin.is_connected()


class TestGoogleDriveTestConnection:
    def test_valid_config_returns_true(self, plugin):
        assert plugin.test_connection(make_config()) is True

    def test_missing_credentials_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestGoogleDriveFetchData:
    def test_returns_query_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult

        result = connected_plugin.fetch_data()
        assert isinstance(result, QueryResult)

    def test_row_count(self, connected_plugin):
        result = connected_plugin.fetch_data()
        assert result.row_count == 2

    def test_columns_include_id_and_name(self, connected_plugin):
        result = connected_plugin.fetch_data()
        assert "id" in result.columns
        assert "name" in result.columns

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()


class TestGoogleDriveFetchIncremental:
    def test_returns_result_with_time_filter(self, connected_plugin):
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = connected_plugin.fetch_incremental(since)
        assert "modifiedTime" in result.query

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestGoogleDriveDiscoverSchema:
    def test_returns_dict_with_keys(self, connected_plugin):
        schema = connected_plugin.discover_schema()
        assert "total_files" in schema
        assert "mime_types" in schema
        assert "folders" in schema

    def test_folder_listed(self, connected_plugin):
        schema = connected_plugin.discover_schema()
        names = [f["name"] for f in schema["folders"]]
        assert "Archive" in names

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()
