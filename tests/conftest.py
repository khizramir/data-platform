import pytest
from unittest.mock import MagicMock, patch

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult
from data_platform.core.plugin_registry import PluginRegistry
from data_platform.core.plugin_manager import PluginManager


class DummyPlugin(DataSourcePlugin):
    _META = PluginMetadata(
        name="dummy",
        version="0.1.0",
        description="Test plugin",
        author="Tests",
        supported_schemes=["dummy"],
    )

    def __init__(self) -> None:
        self._connected = False

    @property
    def metadata(self) -> PluginMetadata:
        return self._META

    def connect(self, config):
        self._connected = True

    def disconnect(self):
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def validate_config(self, config):
        if "dsn" not in config:
            raise ValueError("'dsn' is required")

    def fetch_data(self, query, params=None):
        return QueryResult(columns=["id"], rows=[(1,)], row_count=1, query=query)

    def test_connection(self, config) -> bool:
        return True


class AnotherPlugin(DataSourcePlugin):
    _META = PluginMetadata(name="another", version="0.1.0", description="Another test plugin")

    def __init__(self) -> None:
        self._connected = False

    @property
    def metadata(self):
        return self._META

    def connect(self, config):
        self._connected = True

    def disconnect(self):
        self._connected = False

    def is_connected(self):
        return self._connected

    def validate_config(self, config):
        pass

    def fetch_data(self, query, params=None):
        return QueryResult.empty(query)

    def test_connection(self, config):
        return True


@pytest.fixture
def registry():
    return PluginRegistry()


@pytest.fixture
def registry_with_dummy():
    r = PluginRegistry()
    r.register(DummyPlugin)
    return r


@pytest.fixture
def manager():
    return PluginManager()


@pytest.fixture
def manager_with_dummy():
    m = PluginManager()
    m.register_plugin(DummyPlugin)
    return m


@pytest.fixture
def valid_pg_config():
    return {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "user": "testuser",
        "password": "secret",
    }
