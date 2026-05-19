"""Google Drive plugin for the data integration platform."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class GoogleDrivePlugin(DataSourcePlugin):
    """Extracts files and metadata from Google Drive via the Drive API v3.

    Supports full listing, incremental (changed since timestamp), and schema
    discovery for folder structures. Uses OAuth2 service account or user credentials.
    """

    _METADATA = PluginMetadata(
        name="google_drive",
        version="1.0.0",
        description="Extracts files and metadata from Google Drive",
        author="Data Platform",
        supported_schemes=["gdrive", "https"],
    )

    _FILE_FIELDS = (
        "id,name,mimeType,size,createdTime,modifiedTime,"
        "parents,owners,shared,webViewLink"
    )

    def __init__(self) -> None:
        """Initialize Google Drive plugin."""
        self._config: dict[str, Any] = {}
        self._service: Any = None
        self._connected: bool = False

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate configuration dictionary.

        Args:
            config: Must contain 'credentials_file' or 'access_token'.
                    Optional: 'folder_id' (default 'root').

        Raises:
            ValueError: If neither credentials source is provided.
        """
        if "credentials_file" not in config and "access_token" not in config:
            raise ValueError(
                "Config must contain 'credentials_file' or 'access_token'"
            )

    def connect(self, config: dict[str, Any]) -> None:
        """Authenticate and create Drive API service.

        Args:
            config: Configuration dictionary (see validate_config).
        """
        self.validate_config(config)
        self._config = config
        self._service = self._build_service(config)
        self._connected = True

    def disconnect(self) -> None:
        """Close the Drive API connection."""
        self._connected = False
        self._service = None
        self._config = {}

    def is_connected(self) -> bool:
        """Return True if authenticated service is available."""
        return self._connected and self._service is not None

    def fetch_data(self, query: str = "", params: Any = None) -> QueryResult:
        """Fetch all files from Google Drive.

        Args:
            query: Optional Drive query string (e.g., "mimeType='application/pdf'").
            params: Unused.

        Returns:
            QueryResult with one row per file and file metadata columns.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")

        folder_id = self._config.get("folder_id", "root")
        drive_query = query or f"'{folder_id}' in parents and trashed=false"
        files = self._list_files(drive_query)
        return self._files_to_result(files, query=drive_query)

    def fetch_incremental(self, since: datetime, query: str = "") -> QueryResult:
        """Fetch files modified after a given timestamp.

        Args:
            since: Only files with modifiedTime > this timestamp are returned.
            query: Additional Drive query string.

        Returns:
            QueryResult with recently modified files.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")

        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        folder_id = self._config.get("folder_id", "root")
        time_filter = f"modifiedTime > '{since_str}' and trashed=false"
        drive_query = (
            f"({query}) and {time_filter}" if query
            else f"'{folder_id}' in parents and {time_filter}"
        )
        files = self._list_files(drive_query)
        return self._files_to_result(files, query=drive_query)

    def discover_schema(self, folder_id: str = "") -> dict[str, Any]:
        """Discover folder structure and MIME type distribution.

        Args:
            folder_id: Folder to introspect (uses config 'folder_id' if empty).

        Returns:
            Dict with 'folders', 'mime_types', and 'total_files'.
        """
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")

        fid = folder_id or self._config.get("folder_id", "root")
        all_files = self._list_files(f"'{fid}' in parents and trashed=false")
        mime_counts: dict[str, int] = {}
        folders = []
        for f in all_files:
            mt = f.get("mimeType", "unknown")
            mime_counts[mt] = mime_counts.get(mt, 0) + 1
            if mt == "application/vnd.google-apps.folder":
                folders.append({"id": f.get("id"), "name": f.get("name")})

        return {
            "root_folder_id": fid,
            "total_files": len(all_files),
            "mime_types": mime_counts,
            "folders": folders,
            "columns": self._FILE_FIELDS.split(","),
        }

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test Drive API connectivity.

        Args:
            config: Configuration dictionary.

        Returns:
            True if the service responds successfully.
        """
        try:
            self.validate_config(config)
            svc = self._build_service(config)
            svc.about().get(fields="user").execute()
            return True
        except Exception:
            return False

    def _build_service(self, config: dict[str, Any]) -> Any:
        """Build the Drive API service client.

        Args:
            config: Configuration dictionary.

        Returns:
            Google API client service object or stub.
        """
        if "_service_stub" in config:
            return config["_service_stub"]
        try:
            from google.oauth2.service_account import Credentials  # type: ignore[import]
            from googleapiclient.discovery import build  # type: ignore[import]

            creds = Credentials.from_service_account_file(
                config["credentials_file"],
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
            return build("drive", "v3", credentials=creds)
        except ImportError:
            raise RuntimeError(
                "google-auth and google-api-python-client packages are required"
            )

    def _list_files(self, query: str) -> list[dict[str, Any]]:
        """Page through Drive API results and return all matching files.

        Args:
            query: Drive API query string.

        Returns:
            List of file resource dicts.
        """
        all_files: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            kwargs: dict[str, Any] = {
                "q": query,
                "fields": f"nextPageToken,files({self._FILE_FIELDS})",
                "pageSize": 1000,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            response = self._service.files().list(**kwargs).execute()
            all_files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return all_files

    def _files_to_result(self, files: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert file resource list to QueryResult.

        Args:
            files: List of Drive file resource dicts.
            query: Original query string.

        Returns:
            QueryResult with standardised column order.
        """
        columns = [
            "id", "name", "mimeType", "size", "createdTime",
            "modifiedTime", "parents", "owners", "shared", "webViewLink",
        ]
        rows = [
            tuple(
                json.dumps(f.get(col)) if isinstance(f.get(col), (list, dict))
                else f.get(col)
                for col in columns
            )
            for f in files
        ]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
