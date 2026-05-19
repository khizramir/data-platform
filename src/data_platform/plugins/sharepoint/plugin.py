"""SharePoint plugin for the data integration platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class SharePointPlugin(DataSourcePlugin):
    """Extracts documents and metadata from SharePoint Online via Microsoft Graph API."""

    _METADATA = PluginMetadata(
        name="sharepoint", version="1.0.0",
        description="Extracts documents and metadata from SharePoint Online",
        author="Data Platform", supported_schemes=["sharepoint", "https"],
    )
    _GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self) -> None:
        """Initialize SharePoint plugin."""
        self._config: dict[str, Any] = {}
        self._session: Any = None
        self._connected: bool = False
        self._delta_token: str | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate config. Requires 'access_token' and 'site_id'.

        Args:
            config: Configuration dictionary.

        Raises:
            ValueError: If required keys are missing.
        """
        missing = [k for k in ("access_token", "site_id") if k not in config]
        if missing:
            raise ValueError(f"Config missing required keys: {missing}")

    def connect(self, config: dict[str, Any]) -> None:
        """Authenticate and create Graph API session."""
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
        """List all items in a SharePoint document library."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        site_id = self._config["site_id"]
        drive_id = self._config.get("drive_id", "")
        folder_path = query or self._config.get("folder_path", "")
        items, delta_token = self._list_items(site_id, drive_id, folder_path)
        self._delta_token = delta_token
        return self._items_to_result(items, query=f"site:{site_id}/{folder_path or 'root'}")

    def fetch_incremental(self, since: datetime, folder_path: str = "") -> QueryResult:
        """Fetch items changed since last delta token."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        if not self._delta_token:
            return self.fetch_data(query=folder_path)
        items = self._delta_continue(self._delta_token)
        return self._items_to_result(items, query=f"delta:{folder_path or 'root'}")

    def list_document_libraries(self) -> list[dict[str, Any]]:
        """List all document libraries in the configured site."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        resp = self._session.get(f"{self._GRAPH_BASE}/sites/{self._config['site_id']}/drives")
        resp.raise_for_status()
        return resp.json().get("value", [])

    def discover_schema(self, folder_path: str = "") -> dict[str, Any]:
        """Discover site structure and file type distribution."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        site_id = self._config["site_id"]
        drive_id = self._config.get("drive_id", "")
        path = folder_path or self._config.get("folder_path", "")
        items, _ = self._list_items(site_id, drive_id, path)
        subfolders, mime_counts = [], {}
        for item in items:
            if "folder" in item:
                subfolders.append({"id": item.get("id"), "name": item.get("name")})
            else:
                mime = item.get("file", {}).get("mimeType", "unknown")
                mime_counts[mime] = mime_counts.get(mime, 0) + 1
        return {"site_id": site_id, "folder_path": path or "root", "total_items": len(items),
                "subfolders": subfolders, "mime_types": mime_counts,
                "columns": ["id","name","size","createdDateTime","lastModifiedDateTime","webUrl","mimeType","is_folder","eTag"]}

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test Graph API connectivity to the site."""
        try:
            self.validate_config(config)
            return self._build_session(config).get(f"{self._GRAPH_BASE}/sites/{config['site_id']}").status_code == 200
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

    def _list_items(self, site_id: str, drive_id: str, folder_path: str) -> tuple[list[dict[str, Any]], str]:
        """List all items using delta API."""
        base = (f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}" if drive_id
                else f"{self._GRAPH_BASE}/sites/{site_id}/drive")
        url = (f"{base}/root:/{quote(folder_path)}:/delta" if folder_path else f"{base}/root/delta")
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
        site_id = self._config["site_id"]
        drive_id = self._config.get("drive_id", "")
        base = (f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}" if drive_id
                else f"{self._GRAPH_BASE}/sites/{site_id}/drive")
        url = f"{base}/root/delta(token='{token}')"
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
        columns = ["id","name","size","createdDateTime","lastModifiedDateTime","webUrl","mimeType","is_folder","eTag"]
        rows = []
        for item in items:
            mime = item.get("file", {}).get("mimeType") if "file" in item else None
            rows.append((item.get("id"), item.get("name"), item.get("size"),
                         item.get("createdDateTime"), item.get("lastModifiedDateTime"),
                         item.get("webUrl"), mime, "folder" in item, item.get("eTag")))
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
