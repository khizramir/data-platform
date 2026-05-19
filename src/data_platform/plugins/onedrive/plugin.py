"""OneDrive plugin for the data integration platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class OneDrivePlugin(DataSourcePlugin):
    """Extracts files and metadata from Microsoft OneDrive via Microsoft Graph API."""

    _METADATA = PluginMetadata(
        name="onedrive", version="1.0.0",
        description="Extracts files and metadata from Microsoft OneDrive",
        author="Data Platform", supported_schemes=["onedrive", "https"],
    )
    _GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self) -> None:
        """Initialize OneDrive plugin."""
        self._config: dict[str, Any] = {}
        self._session: Any = None
        self._connected: bool = False
        self._delta_token: str | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate config. Requires 'access_token'.

        Args:
            config: Configuration dictionary.

        Raises:
            ValueError: If 'access_token' is missing.
        """
        if "access_token" not in config:
            raise ValueError("Config missing required key: 'access_token'")

    def connect(self, config: dict[str, Any]) -> None:
        """Authenticate and create Graph API session.

        Args:
            config: Configuration dictionary.
        """
        self.validate_config(config)
        self._config = config
        self._session = self._build_session(config)
        self._connected = True

    def disconnect(self) -> None:
        """Close the Graph API session."""
        self._connected = False
        self._session = None
        self._config = {}
        self._delta_token = None

    def is_connected(self) -> bool:
        """Return True if an authenticated session exists."""
        return self._connected and self._session is not None

    def fetch_data(self, query: str = "", params: Any = None) -> QueryResult:
        """List all items in the configured OneDrive folder.

        Args:
            query: Optional folder path override.
            params: Unused.

        Returns:
            QueryResult with one row per drive item.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        folder_path = query or self._config.get("folder_path", "root")
        items, delta_token = self._list_items(folder_path)
        self._delta_token = delta_token
        return self._items_to_result(items, query=folder_path)

    def fetch_incremental(self, since: datetime, folder_path: str = "") -> QueryResult:
        """Fetch items changed since last delta token.

        Args:
            since: Unused — uses delta token tracking.
            folder_path: Folder path override.

        Returns:
            QueryResult with changed items.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        if not self._delta_token:
            return self.fetch_data(query=folder_path)
        items = self._delta_continue(self._delta_token)
        path = folder_path or self._config.get("folder_path", "root")
        return self._items_to_result(items, query=f"delta:{path}")

    def discover_schema(self, folder_path: str = "") -> dict[str, Any]:
        """Discover folder structure and file type distribution.

        Args:
            folder_path: Folder to introspect.

        Returns:
            Dict with subfolders, mime_types, total_items.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        path = folder_path or self._config.get("folder_path", "root")
        items, _ = self._list_items(path)
        subfolders, mime_counts = [], {}
        for item in items:
            if "folder" in item:
                subfolders.append({"id": item.get("id"), "name": item.get("name")})
            else:
                mime = item.get("file", {}).get("mimeType", "unknown")
                mime_counts[mime] = mime_counts.get(mime, 0) + 1
        return {"folder_path": path, "total_items": len(items),
                "subfolders": subfolders, "mime_types": mime_counts,
                "columns": ["id","name","size","createdDateTime","lastModifiedDateTime","webUrl","mimeType","is_folder"]}

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test Graph API connectivity.

        Args:
            config: Configuration dictionary.

        Returns:
            True if me/drive endpoint responds.
        """
        try:
            self.validate_config(config)
            resp = self._build_session(config).get(f"{self._GRAPH_BASE}/me/drive")
            return resp.status_code == 200
        except Exception:
            return False

    def _build_session(self, config: dict[str, Any]) -> Any:
        """Build authenticated HTTP session."""
        if "_session_stub" in config:
            return config["_session_stub"]
        import requests  # type: ignore[import]
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {config['access_token']}"
        s.headers["Accept"] = "application/json"
        return s

    def _list_items(self, folder_path: str) -> tuple[list[dict[str, Any]], str]:
        """List all items using delta API."""
        url = (f"{self._GRAPH_BASE}/me/drive/root/delta" if folder_path == "root"
               else f"{self._GRAPH_BASE}/me/drive/root:/{folder_path}:/delta")
        items, delta_token = [], ""
        while url:
            resp = self._session.get(url)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink", "")
            if dl := data.get("@odata.deltaLink", ""):
                delta_token = self._extract_delta_token(dl)
        return items, delta_token

    def _delta_continue(self, token: str) -> list[dict[str, Any]]:
        """Fetch changed items using a delta token."""
        url = f"{self._GRAPH_BASE}/me/drive/root/delta(token='{token}')"
        items = []
        while url:
            resp = self._session.get(url)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink", "")
            if dl := data.get("@odata.deltaLink", ""):
                self._delta_token = self._extract_delta_token(dl)
        return items

    @staticmethod
    def _extract_delta_token(delta_link: str) -> str:
        """Extract bare token from Graph delta link."""
        if "token=" in delta_link:
            return delta_link.split("token=")[-1].strip("'\")(")
        return delta_link

    def _items_to_result(self, items: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert item list to QueryResult."""
        columns = ["id","name","size","createdDateTime","lastModifiedDateTime","webUrl","mimeType","is_folder"]
        rows = []
        for item in items:
            mime = item.get("file", {}).get("mimeType") if "file" in item else None
            rows.append((item.get("id"), item.get("name"), item.get("size"),
                         item.get("createdDateTime"), item.get("lastModifiedDateTime"),
                         item.get("webUrl"), mime, "folder" in item))
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
