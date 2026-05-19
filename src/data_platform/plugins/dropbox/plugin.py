"""Dropbox plugin for the data integration platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class DropboxPlugin(DataSourcePlugin):
    """Extracts files and metadata from Dropbox via the Dropbox API v2.

    Supports full listing of a folder tree, incremental extraction via Dropbox
    cursors, and schema discovery of folder hierarchies.
    """

    _METADATA = PluginMetadata(
        name="dropbox",
        version="1.0.0",
        description="Extracts files and metadata from Dropbox",
        author="Data Platform",
        supported_schemes=["dropbox", "https"],
    )

    _API_BASE = "https://api.dropboxapi.com/2"

    def __init__(self) -> None:
        """Initialize Dropbox plugin."""
        self._config: dict[str, Any] = {}
        self._session: Any = None
        self._connected: bool = False
        self._cursor: str | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate configuration dictionary.

        Args:
            config: Must contain 'access_token'. Optional: 'folder_path'.

        Raises:
            ValueError: If 'access_token' is missing.
        """
        if "access_token" not in config:
            raise ValueError("Config missing required key: 'access_token'")

    def connect(self, config: dict[str, Any]) -> None:
        """Authenticate and create Dropbox API session.

        Args:
            config: Configuration dictionary (see validate_config).
        """
        self.validate_config(config)
        self._config = config
        self._session = self._build_session(config)
        self._connected = True

    def disconnect(self) -> None:
        """Close the Dropbox API session."""
        self._connected = False
        self._session = None
        self._config = {}
        self._cursor = None

    def is_connected(self) -> bool:
        """Return True if an authenticated session exists."""
        return self._connected and self._session is not None

    def fetch_data(self, query: str = "", params: Any = None) -> QueryResult:
        """List all entries under the configured Dropbox folder.

        Args:
            query: Optional folder path override (e.g., '/Documents').
            params: Unused.

        Returns:
            QueryResult with one row per Dropbox entry.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")

        folder = query or self._config.get("folder_path", "")
        entries, cursor = self._list_folder(folder, recursive=True)
        self._cursor = cursor
        return self._entries_to_result(entries, query=folder or "/")

    def fetch_incremental(self, since: datetime, folder: str = "") -> QueryResult:
        """Fetch entries changed since last cursor.

        Args:
            since: Unused — Dropbox uses cursor-based tracking.
            folder: Folder path override.

        Returns:
            QueryResult with changed entries since last fetch_data call.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")

        if not self._cursor:
            return self.fetch_data(query=folder)

        entries = self._list_folder_continue(self._cursor)
        folder_path = folder or self._config.get("folder_path", "/")
        return self._entries_to_result(entries, query=f"incremental:{folder_path}")

    def discover_schema(self, folder: str = "") -> dict[str, Any]:
        """Discover folder structure and file type distribution.

        Args:
            folder: Folder to introspect (uses config default if empty).

        Returns:
            Dict with 'subfolders', 'extensions', and 'total_entries'.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")

        folder = folder or self._config.get("folder_path", "")
        entries, _ = self._list_folder(folder, recursive=False)

        subfolders = []
        ext_counts: dict[str, int] = {}
        for entry in entries:
            if entry.get(".tag") == "folder":
                subfolders.append({"path": entry.get("path_display"), "name": entry.get("name")})
            else:
                name = entry.get("name", "")
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else "no_ext"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

        return {
            "folder_path": folder or "/",
            "total_entries": len(entries),
            "subfolders": subfolders,
            "file_extensions": ext_counts,
            "columns": [
                ".tag", "id", "name", "path_display",
                "size", "client_modified", "server_modified", "content_hash",
            ],
        }

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test Dropbox API connectivity.

        Args:
            config: Configuration dictionary.

        Returns:
            True if the account info endpoint responds successfully.
        """
        try:
            self.validate_config(config)
            session = self._build_session(config)
            resp = session.post(f"{self._API_BASE}/users/get_current_account")
            return resp.status_code == 200
        except Exception:
            return False

    def _build_session(self, config: dict[str, Any]) -> Any:
        """Build an authenticated HTTP session for the Dropbox API."""
        if "_session_stub" in config:
            return config["_session_stub"]

        import requests  # type: ignore[import]

        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {config['access_token']}"
        session.headers["Content-Type"] = "application/json"
        return session

    def _list_folder(self, path: str, recursive: bool = True) -> tuple[list[dict[str, Any]], str]:
        """List all entries in a Dropbox folder."""
        payload: dict[str, Any] = {
            "path": path,
            "recursive": recursive,
            "include_deleted": False,
            "limit": 2000,
        }
        resp = self._session.post(f"{self._API_BASE}/files/list_folder", json=payload)
        resp.raise_for_status()
        data = resp.json()

        entries = list(data.get("entries", []))
        cursor = data.get("cursor", "")
        has_more = data.get("has_more", False)

        while has_more:
            resp = self._session.post(
                f"{self._API_BASE}/files/list_folder/continue",
                json={"cursor": cursor},
            )
            resp.raise_for_status()
            data = resp.json()
            entries.extend(data.get("entries", []))
            cursor = data.get("cursor", cursor)
            has_more = data.get("has_more", False)

        return entries, cursor

    def _list_folder_continue(self, cursor: str) -> list[dict[str, Any]]:
        """Continue a folder listing from a saved cursor."""
        entries: list[dict[str, Any]] = []
        has_more = True

        while has_more:
            resp = self._session.post(
                f"{self._API_BASE}/files/list_folder/continue",
                json={"cursor": cursor},
            )
            resp.raise_for_status()
            data = resp.json()
            entries.extend(data.get("entries", []))
            cursor = data.get("cursor", cursor)
            has_more = data.get("has_more", False)

        self._cursor = cursor
        return entries

    def _entries_to_result(self, entries: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert Dropbox entry list to QueryResult."""
        columns = [
            ".tag", "id", "name", "path_display",
            "size", "client_modified", "server_modified", "content_hash",
        ]
        rows = [tuple(entry.get(col) for col in columns) for entry in entries]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
