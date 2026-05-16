import pytest
from unittest.mock import MagicMock, patch

from data_platform.plugins.postgresql.plugin import PostgreSQLPlugin
from data_platform.core.base_plugin import QueryResult


@pytest.fixture
def plugin():
    return PostgreSQLPlugin()


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    conn.closed = 0  # 0 = open in psycopg2
    return conn


@pytest.fixture
def connected_plugin(plugin, valid_pg_config, mock_connection):
    with patch("psycopg2.connect", return_value=mock_connection):
        plugin.connect(valid_pg_config)
    return plugin, mock_connection


class TestPostgreSQLPluginMetadata:
    def test_name(self, plugin):
        assert plugin.metadata.name == "postgresql"

    def test_version(self, plugin):
        assert plugin.metadata.version == "1.0.0"

    def test_supported_schemes(self, plugin):
        assert "postgresql" in plugin.metadata.supported_schemes
        assert "postgres" in plugin.metadata.supported_schemes


class TestPostgreSQLPluginValidateConfig:
    def test_valid_config_passes(self, plugin, valid_pg_config):
        plugin.validate_config(valid_pg_config)

    @pytest.mark.parametrize("missing_key", ["host", "port", "database", "user", "password"])
    def test_missing_required_key_raises(self, plugin, valid_pg_config, missing_key):
        del valid_pg_config[missing_key]
        with pytest.raises(ValueError, match=missing_key):
            plugin.validate_config(valid_pg_config)

    def test_port_must_be_int(self, plugin, valid_pg_config):
        valid_pg_config["port"] = "5432"
        with pytest.raises(ValueError, match="port"):
            plugin.validate_config(valid_pg_config)


class TestPostgreSQLPluginConnect:
    def test_connect_calls_psycopg2(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection) as mock_connect:
            plugin.connect(valid_pg_config)
            call_kwargs = mock_connect.call_args.kwargs
            assert call_kwargs["host"] == "localhost"
            assert call_kwargs["port"] == 5432
            assert call_kwargs["dbname"] == "testdb"

    def test_connect_sets_is_connected(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection):
            plugin.connect(valid_pg_config)
        assert plugin.is_connected()

    def test_connect_twice_raises(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection):
            plugin.connect(valid_pg_config)
            with pytest.raises(RuntimeError, match="Already connected"):
                plugin.connect(valid_pg_config)

    def test_connect_sets_autocommit_default_false(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection):
            plugin.connect(valid_pg_config)
        assert mock_connection.autocommit is False

    def test_connect_respects_autocommit_option(self, plugin, valid_pg_config, mock_connection):
        valid_pg_config["autocommit"] = True
        with patch("psycopg2.connect", return_value=mock_connection):
            plugin.connect(valid_pg_config)
        assert mock_connection.autocommit is True


class TestPostgreSQLPluginDisconnect:
    def test_disconnect_closes_connection(self, connected_plugin):
        plugin, conn = connected_plugin
        plugin.disconnect()
        conn.close.assert_called_once()

    def test_disconnect_sets_not_connected(self, connected_plugin):
        plugin, conn = connected_plugin
        conn.closed = 1
        plugin.disconnect()
        assert not plugin.is_connected()

    def test_disconnect_when_not_connected_is_noop(self, plugin):
        plugin.disconnect()


class TestPostgreSQLPluginIsConnected:
    def test_false_when_no_connection(self, plugin):
        assert not plugin.is_connected()

    def test_true_when_connection_open(self, connected_plugin):
        plugin, conn = connected_plugin
        conn.closed = 0
        assert plugin.is_connected()

    def test_false_when_connection_closed(self, connected_plugin):
        plugin, conn = connected_plugin
        conn.closed = 1
        assert not plugin.is_connected()


class TestPostgreSQLPluginFetchData:
    def test_fetch_data_executes_query(self, connected_plugin):
        plugin, conn = connected_plugin
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        cursor.rowcount = 2
        result = plugin.fetch_data("SELECT id, name FROM users")
        cursor.execute.assert_called_once_with("SELECT id, name FROM users", None)
        assert result.columns == ["id", "name"]
        assert result.rows == [(1, "Alice"), (2, "Bob")]
        assert result.row_count == 2

    def test_fetch_data_with_params(self, connected_plugin):
        plugin, conn = connected_plugin
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.description = [("id",)]
        cursor.fetchall.return_value = [(1,)]
        cursor.rowcount = 1
        result = plugin.fetch_data("SELECT id FROM users WHERE id = %s", (1,))
        cursor.execute.assert_called_once_with("SELECT id FROM users WHERE id = %s", (1,))
        assert result.rows == [(1,)]

    def test_fetch_data_no_description_returns_empty_columns(self, connected_plugin):
        plugin, conn = connected_plugin
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.description = None
        cursor.rowcount = -1
        result = plugin.fetch_data("CREATE TABLE foo (id INT)")
        assert result.columns == []
        assert result.rows == []

    def test_fetch_data_not_connected_raises(self, plugin):
        with pytest.raises(RuntimeError, match="Not connected"):
            plugin.fetch_data("SELECT 1")


class TestPostgreSQLPluginTestConnection:
    def test_returns_true_on_success(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection):
            assert plugin.test_connection(valid_pg_config) is True

    def test_closes_test_connection(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection):
            plugin.test_connection(valid_pg_config)
        mock_connection.close.assert_called_once()

    def test_returns_false_on_connection_error(self, plugin, valid_pg_config):
        with patch("psycopg2.connect", side_effect=Exception("connection refused")):
            assert plugin.test_connection(valid_pg_config) is False


class TestPostgreSQLPluginContextManager:
    def test_context_manager_disconnects(self, plugin, valid_pg_config, mock_connection):
        with patch("psycopg2.connect", return_value=mock_connection):
            with plugin as p:
                p.connect(valid_pg_config)
                assert p.is_connected()
        mock_connection.close.assert_called_once()
