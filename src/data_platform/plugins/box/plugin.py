"""Box plugin for the data integration platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class BoxPlugin(DataSourcePlugin):
    """Extracts files and metadata from Box via the Box Content API v2."""

    _METADATA = PluginMetadata(
        name="box", version="1.0.0",
        description="Extracts files and metadata from Box",
        author="Data Platform", supported_schemes=["box", "https"],
    )
    _API_BASE = "https://api.box.com/2.0"

    def __init__(self) -> None:
        """Initialize Box plugin."""
        self._config: dict[str, Any] = {}
        self._session: Any = None
        self._connected: bool = False
        self._stream_position: str = "0"

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
        """Authenticate and create Box API session.

        Args:
            config: Configuration dictionary.
        """
        self.validate_config(config)
        self._config = config
        self._session = self._build_session(config)
        self._connected = True

    def disconnect(self) -> None:
        """Close the Box API session."""
        self._connected = False
        self._session = None
        self._config = {}
        self._stream_position = "0"

    def is_connected(self) -> bool:
        """Return True if an authenticated session exists."""
        return self._connected and self._session is not None

    def fetch_data(self, query: str = "", params: Any = None) -> QueryResult:
        """List all items in a Box folder.

        Args:
            query: Optional folder ID override.
            params: Unused.

        Returns:
            QueryResult with one row per Box item.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        folder_id = query or self._config.get("folder_id", "0")
        items = self._list_folder(folder_id)
        return self._items_to_result(items, query=f"folder:{folder_id}")

    def fetch_incremental(self, since: datetime, event_types: str = "") -> QueryResult:
        """Fetch Box events since the last stream position.

        Args:
            since: Unused — uses stream_position tracking.
            event_types: Comma-separated event type filter.

        Returns:
            QueryResult with events.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        events, next_position = self._get_events(self._stream_position, event_types)
        self._stream_position = next_position
        return self._events_to_result(events, query=f"events:position={self._stream_position}")

    def discover_schema(self, folder_id: str = "") -> dict[str, Any]:
        """Discover folder structure and item type distribution.

        Args:
            folder_id: Box folder ID to introspect.

        Returns:
            Dict with subfolders, item_types, total_items.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        fid = folder_id or self._config.get("folder_id", "0")
        items = self._list_folder(fid)
        subfolders, type_counts = [], {}
        for item in items:
            t = item.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
            if t == "folder":
                subfolders.append({"id": item.get("id"), "name": item.get("name")})
        return {"folder_id": fid, "total_items": len(items), "subfolders": subfolders,
                "item_types": type_counts,
                "columns": ["id","type","name","size","created_at","modified_at","owned_by","shared_link","etag"]}

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test Box API connectivity.

        Args:
            config: Configuration dictionary.

        Returns:
            True if users/me responds.
        """
        try:
            self.validate_config(config)
            return self._build_session(config).get(f"{self._API_BASE}/users/me").status_code == 200
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

    def _list_folder(self, folder_id: str) -> list[dict[str, Any]]:
        """List all items in a Box folder with pagination."""
        items, offset, limit = [], 0, 1000
        while True:
            resp = self._session.get(f"{self._API_BASE}/folders/{folder_id}/items",
                params={"limit": limit, "offset": offset,
                        "fields": "id,type,name,size,created_at,modified_at,owned_by,shared_link,etag"})
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("entries", [])
            items.extend(entries)
            total_count = data.get("total_count", 0)
            offset += len(entries)
            if offset >= total_count or not entries:
                break
        return items

    def _get_events(self, stream_position: str, event_types: str) -> tuple[list[dict[str, Any]], str]:
        """Fetch events from Box Events API."""
        params: dict[str, Any] = {"stream_type": "changes", "stream_position": stream_position, "limit": 500}
        if event_types:
            params["event_type"] = event_types
        resp = self._session.get(f"{self._API_BASE}/events", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("entries", []), str(data.get("next_stream_position", stream_position))

    def _items_to_result(self, items: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert Box item list to QueryResult."""
        columns = ["id","type","name","size","created_at","modified_at","owned_by","shared_link","etag"]
        rows = []
        for item in items:
            ob = item.get("owned_by", {})
            rows.append((item.get("id"), item.get("type"), item.get("name"), item.get("size"),
                         item.get("created_at"), item.get("modified_at"),
                         ob.get("name") if isinstance(ob, dict) else ob,
                         item.get("shared_link"), item.get("etag")))
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)

    def _events_to_result(self, events: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert Box event list to QueryResult."""
        columns = ["event_id","event_type","created_at","created_by","source_id","source_name"]
        rows = []
        for evt in events:
            cb = evt.get("created_by", {})
            src = evt.get("source", {})
            rows.append((evt.get("event_id"), evt.get("event_type"), evt.get("created_at"),
                         cb.get("name") if isinstance(cb, dict) else cb,
                         src.get("id") if isinstance(src, dict) else None,
                         src.get("name") if isinstance(src, dict) else None))
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
