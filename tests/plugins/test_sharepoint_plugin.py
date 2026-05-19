"""Tests for the SharePoint plugin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from data_platform.plugins.sharepoint.plugin import SharePointPlugin


def make_session_stub(items=None, status=200):
    stub = MagicMock()
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"value": items or [], "@odata.deltaLink": "https://graph.microsoft.com/v1.0/sites/site1/drive/root/delta(token='delta_tok')"}
    resp.raise_for_status = MagicMock()
    stub.get.return_value = resp
    return stub


def make_config(items=None, status=200):
    return {"access_token": "tok", "site_id": "site1", "_session_stub": make_session_stub(items, status)}


SAMPLE_ITEMS = [
    {"id": "doc1", "name": "policy.docx", "size": 30720, "createdDateTime": "2024-01-01T00:00:00Z", "lastModifiedDateTime": "2024-01-02T00:00:00Z", "webUrl": "https://contoso.sharepoint.com/policy.docx", "file": {"mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, "eTag": "etag1"},
    {"id": "folder1", "name": "Policies", "size": None, "createdDateTime": "2024-01-01T00:00:00Z", "lastModifiedDateTime": "2024-01-01T00:00:00Z", "webUrl": "https://contoso.sharepoint.com/Policies", "folder": {"childCount": 10}, "eTag": "etag2"},
]


@pytest.fixture
def plugin():
    return SharePointPlugin()


@pytest.fixture
def connected_plugin(plugin):
    plugin.connect(make_config(SAMPLE_ITEMS))
    return plugin


class TestSharePointMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "sharepoint"

    def test_schemes(self, plugin):
        assert "sharepoint" in plugin.metadata.supported_schemes


class TestSharePointValidateConfig:
    def test_missing_both_raises(self, plugin):
        with pytest.raises(ValueError, match="access_token"):
            plugin.validate_config({})

    def test_missing_site_id_raises(self, plugin):
        with pytest.raises(ValueError, match="site_id"):
            plugin.validate_config({"access_token": "tok"})

    def test_valid_passes(self, plugin):
        plugin.validate_config({"access_token": "tok", "site_id": "s1"})


class TestSharePointConnection:
    def test_not_connected_initially(self, plugin):
        assert not plugin.is_connected()

    def test_connected_after_connect(self, connected_plugin):
        assert connected_plugin.is_connected()

    def test_disconnected(self, connected_plugin):
        connected_plugin.disconnect()
        assert not connected_plugin.is_connected()

    def test_delta_cleared(self, connected_plugin):
        connected_plugin._delta_token = "tok"
        connected_plugin.disconnect()
        assert connected_plugin._delta_token is None

    def test_context_manager(self, plugin):
        with plugin:
            plugin.connect(make_config())
            assert plugin.is_connected()
        assert not plugin.is_connected()


class TestSharePointTestConnection:
    def test_valid_returns_true(self, plugin):
        assert plugin.test_connection(make_config(status=200)) is True

    def test_invalid_returns_false(self, plugin):
        assert plugin.test_connection({}) is False


class TestSharePointFetchData:
    def test_returns_result(self, connected_plugin):
        from data_platform.core.base_plugin import QueryResult
        assert isinstance(connected_plugin.fetch_data(), QueryResult)

    def test_row_count(self, connected_plugin):
        assert connected_plugin.fetch_data().row_count == 2

    def test_delta_token_stored(self, connected_plugin):
        connected_plugin.fetch_data()
        assert connected_plugin._delta_token == "delta_tok"

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_data()

    def test_folder_flagged(self, connected_plugin):
        r = connected_plugin.fetch_data()
        col = r.columns.index("is_folder")
        flags = [row[col] for row in r.rows]
        assert True in flags
        assert False in flags


class TestSharePointFetchIncremental:
    def test_no_token_does_full_fetch(self, connected_plugin):
        connected_plugin._delta_token = None
        assert connected_plugin.fetch_data().row_count == 2

    def test_with_token_uses_delta(self, connected_plugin):
        connected_plugin._delta_token = "tok"
        r = connected_plugin.fetch_incremental(datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert "delta" in r.query

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.fetch_incremental(datetime.now(timezone.utc))


class TestSharePointDiscoverSchema:
    def test_keys(self, connected_plugin):
        s = connected_plugin.discover_schema()
        assert "total_items" in s
        assert "subfolders" in s

    def test_subfolder(self, connected_plugin):
        assert "Policies" in [f["name"] for f in connected_plugin.discover_schema()["subfolders"]]

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.discover_schema()


class TestSharePointListLibraries:
    def test_returns_list(self, connected_plugin):
        stub = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"value": [{"id": "d1", "name": "Documents"}]}
        resp.raise_for_status = MagicMock()
        stub.get.return_value = resp
        connected_plugin._session = stub
        assert isinstance(connected_plugin.list_document_libraries(), list)

    def test_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="not connected"):
            plugin.list_document_libraries()
