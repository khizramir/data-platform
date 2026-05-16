from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult

_REQUIRED_CONFIG_KEYS = ("host", "port", "database", "user", "password")


class PostgreSQLPlugin(DataSourcePlugin):
    """Data source plugin for PostgreSQL databases via psycopg2."""

    _METADATA = PluginMetadata(
        name="postgresql",
        version="1.0.0",
        description="PostgreSQL data source plugin using psycopg2",
        author="Data Platform Team",
        supported_schemes=["postgresql", "postgres"],
    )

    def __init__(self) -> None:
        self._connection: Any = None
        self._config: dict[str, Any] = {}

    @property
    def metadata(self) -> PluginMetadata:
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        missing = [k for k in _REQUIRED_CONFIG_KEYS if k not in config]
        if missing:
            raise ValueError(f"PostgreSQL plugin config missing required keys: {missing}")
        if not isinstance(config.get("port"), int):
            raise ValueError("'port' must be an integer")

    def connect(self, config: dict[str, Any]) -> None:
        if self._connection is not None:
            raise RuntimeError("Already connected. Call disconnect() first.")
        self.validate_config(config)

        import psycopg2  # local import keeps the module usable without psycopg2 at import time

        self._connection = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            dbname=config["database"],
            user=config["user"],
            password=config["password"],
            connect_timeout=config.get("connect_timeout", 10),
            options=config.get("options", ""),
        )
        self._connection.autocommit = config.get("autocommit", False)
        self._config = dict(config)

    def disconnect(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close()
        finally:
            self._connection = None
            self._config = {}

    def is_connected(self) -> bool:
        if self._connection is None:
            return False
        # psycopg2 exposes a `closed` attribute (0 = open)
        return self._connection.closed == 0

    def fetch_data(self, query: str, params: tuple[Any, ...] | None = None) -> QueryResult:
        if not self.is_connected():
            raise RuntimeError("Not connected. Call connect() before fetch_data().")

        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            columns: list[str] = []
            rows: list[tuple[Any, ...]] = []

            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=cursor.rowcount if cursor.rowcount >= 0 else len(rows),
                query=query,
            )

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Return True if a throw-away connection can be opened with *config*."""
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=config["host"],
                port=config["port"],
                dbname=config["database"],
                user=config["user"],
                password=config["password"],
                connect_timeout=config.get("connect_timeout", 5),
            )
            conn.close()
            return True
        except Exception:
            return False
