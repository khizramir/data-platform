import pytest

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult
from conftest import DummyPlugin


class TestPluginMetadata:
    def test_fields_are_stored(self):
        meta = PluginMetadata(
            name="test", version="1.2.3", description="desc",
            author="me", supported_schemes=["s3", "gs"],
        )
        assert meta.name == "test"
        assert meta.version == "1.2.3"
        assert meta.description == "desc"
        assert meta.author == "me"
        assert meta.supported_schemes == ["s3", "gs"]

    def test_is_frozen(self):
        meta = PluginMetadata(name="x", version="1", description="d")
        with pytest.raises((AttributeError, TypeError)):
            meta.name = "y"  # type: ignore[misc]

    def test_defaults(self):
        meta = PluginMetadata(name="x", version="1", description="d")
        assert meta.author == ""
        assert meta.supported_schemes == []


class TestQueryResult:
    def test_fields(self):
        qr = QueryResult(columns=["a", "b"], rows=[(1, 2)], row_count=1, query="SELECT 1")
        assert qr.columns == ["a", "b"]
        assert qr.rows == [(1, 2)]
        assert qr.row_count == 1
        assert qr.query == "SELECT 1"

    def test_empty_factory(self):
        qr = QueryResult.empty("SELECT 0")
        assert qr.columns == []
        assert qr.rows == []
        assert qr.row_count == 0
        assert qr.query == "SELECT 0"

    def test_empty_defaults_query(self):
        qr = QueryResult.empty()
        assert qr.query == ""


class TestDataSourcePluginAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            DataSourcePlugin()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        assert isinstance(DummyPlugin(), DataSourcePlugin)

    def test_metadata_property(self):
        meta = DummyPlugin().metadata
        assert meta.name == "dummy"
        assert meta.version == "0.1.0"


class TestDataSourcePluginLifecycle:
    def test_connect_and_disconnect(self):
        plugin = DummyPlugin()
        assert not plugin.is_connected()
        plugin.connect({"dsn": "dummy://localhost"})
        assert plugin.is_connected()
        plugin.disconnect()
        assert not plugin.is_connected()

    def test_fetch_data_returns_query_result(self):
        plugin = DummyPlugin()
        plugin.connect({"dsn": "dummy://localhost"})
        result = plugin.fetch_data("SELECT 1")
        assert isinstance(result, QueryResult)
        assert result.query == "SELECT 1"

    def test_validate_config_raises_on_missing_key(self):
        with pytest.raises(ValueError, match="dsn"):
            DummyPlugin().validate_config({})

    def test_validate_config_passes_with_valid_config(self):
        DummyPlugin().validate_config({"dsn": "dummy://localhost"})

    def test_test_connection_returns_bool(self):
        assert DummyPlugin().test_connection({"dsn": "dummy://localhost"}) is True


class TestContextManager:
    def test_context_manager_disconnects_on_exit(self):
        plugin = DummyPlugin()
        plugin.connect({"dsn": "dummy://localhost"})
        with plugin as p:
            assert p.is_connected()
        assert not plugin.is_connected()

    def test_context_manager_noop_when_not_connected(self):
        with DummyPlugin():
            pass
