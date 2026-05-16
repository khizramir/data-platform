from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PluginMetadata:
    name: str
    version: str
    description: str
    author: str = ""
    supported_schemes: list[str] = field(default_factory=list)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    query: str

    @classmethod
    def empty(cls, query: str = "") -> "QueryResult":
        return cls(columns=[], rows=[], row_count=0, query=query)


class DataSourcePlugin(ABC):
    """Abstract base class for all data source plugins."""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""

    @abstractmethod
    def connect(self, config: dict[str, Any]) -> None:
        """Establish a connection using the provided config."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the active connection."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the plugin currently holds an open connection."""

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Raise ValueError if config is missing required fields."""

    @abstractmethod
    def fetch_data(self, query: str, params: tuple[Any, ...] | None = None) -> QueryResult:
        """Execute query and return results."""

    @abstractmethod
    def test_connection(self, config: dict[str, Any]) -> bool:
        """Return True if a connection can be established with config."""

    def __enter__(self) -> "DataSourcePlugin":
        return self

    def __exit__(self, *_: Any) -> None:
        if self.is_connected():
            self.disconnect()
