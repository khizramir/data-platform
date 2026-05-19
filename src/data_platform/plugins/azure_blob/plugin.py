"""Azure Blob Storage plugin for the data integration platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class AzureBlobPlugin(DataSourcePlugin):
    """Extracts blob metadata from Azure Blob Storage via the Azure SDK."""

    _METADATA = PluginMetadata(
        name="azure_blob", version="1.0.0",
        description="Extracts blob metadata from Azure Blob Storage",
        author="Data Platform", supported_schemes=["abfs", "wasbs", "https"],
    )

    def __init__(self) -> None:
        """Initialize Azure Blob Storage plugin."""
        self._config: dict[str, Any] = {}
        self._client: Any = None
        self._connected: bool = False

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate config. Requires 'container_name' and credentials."""
        if "container_name" not in config:
            raise ValueError("Config missing required key: 'container_name'")
        has_conn_str = "connection_string" in config
        has_key = "account_name" in config and "account_key" in config
        has_sas = "account_name" in config and "sas_token" in config
        if not (has_conn_str or has_key or has_sas):
            raise ValueError("Config must contain 'connection_string', or 'account_name'+'account_key', or 'account_name'+'sas_token'")

    def connect(self, config: dict[str, Any]) -> None:
        """Build Azure Blob container client."""
        self.validate_config(config)
        self._config = config
        self._client = self._build_client(config)
        self._connected = True

    def disconnect(self) -> None:
        """Release the Azure Blob container client."""
        self._connected = False
        self._client = None
        self._config = {}

    def is_connected(self) -> bool:
        """Return True if a container client is available."""
        return self._connected and self._client is not None

    def fetch_data(self, query: str = "", params: Any = None) -> QueryResult:
        """List all blobs in the configured container."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        prefix = query or self._config.get("prefix", "")
        blobs = self._list_blobs(prefix)
        container = self._config["container_name"]
        return self._blobs_to_result(blobs, query=f"azure://{container}/{prefix}")

    def fetch_incremental(self, since: datetime, prefix: str = "") -> QueryResult:
        """Fetch blobs modified after a given timestamp."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        effective_prefix = prefix or self._config.get("prefix", "")
        all_blobs = self._list_blobs(effective_prefix)
        filtered = [b for b in all_blobs
                    if b.get("last_modified") and b["last_modified"].replace(tzinfo=None) > since.replace(tzinfo=None)]
        container = self._config["container_name"]
        return self._blobs_to_result(filtered, query=f"azure://{container}/{effective_prefix}?since={since.isoformat()}")

    def discover_schema(self, prefix: str = "") -> dict[str, Any]:
        """Discover virtual directory structure and blob type distribution."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        effective_prefix = prefix or self._config.get("prefix", "")
        blobs = self._list_blobs(effective_prefix)
        virtual_dirs: set[str] = set()
        content_type_counts: dict[str, int] = {}
        for blob in blobs:
            name = blob.get("name", "")
            parts = name.split("/")
            if len(parts) > 1:
                virtual_dirs.add("/".join(parts[:-1]) + "/")
            ct = blob.get("content_type", "unknown") or "unknown"
            content_type_counts[ct] = content_type_counts.get(ct, 0) + 1
        container = self._config["container_name"]
        return {"container": container, "prefix": effective_prefix, "total_blobs": len(blobs),
                "virtual_dirs": sorted(virtual_dirs), "content_types": content_type_counts,
                "columns": ["name","size","last_modified","content_type","etag","blob_type","lease_status"]}

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test Azure Blob connectivity."""
        try:
            self.validate_config(config)
            self._build_client(config).exists()
            return True
        except Exception:
            return False

    def _build_client(self, config: dict[str, Any]) -> Any:
        """Build ContainerClient from config."""
        if "_client_stub" in config:
            return config["_client_stub"]
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore[import]
            if "connection_string" in config:
                service = BlobServiceClient.from_connection_string(config["connection_string"])
            elif "account_key" in config:
                account_url = f"https://{config['account_name']}.blob.core.windows.net"
                service = BlobServiceClient(account_url=account_url, credential=config["account_key"])
            else:
                account_url = f"https://{config['account_name']}.blob.core.windows.net"
                service = BlobServiceClient(account_url=account_url, credential=config["sas_token"])
            return service.get_container_client(config["container_name"])
        except ImportError:
            raise RuntimeError("azure-storage-blob package is required for the Azure Blob plugin")

    def _list_blobs(self, prefix: str) -> list[dict[str, Any]]:
        """List all blobs matching a prefix."""
        kwargs: dict[str, Any] = {}
        if prefix:
            kwargs["name_starts_with"] = prefix
        blobs = []
        for blob in self._client.list_blobs(**kwargs):
            blobs.append({
                "name": blob.name, "size": blob.size, "last_modified": blob.last_modified,
                "content_type": blob.content_settings.content_type if blob.content_settings else None,
                "etag": blob.etag,
                "blob_type": str(blob.blob_type) if blob.blob_type else None,
                "lease_status": str(blob.lease.status) if blob.lease else None,
            })
        return blobs

    def _blobs_to_result(self, blobs: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert blob list to QueryResult."""
        columns = ["name","size","last_modified","content_type","etag","blob_type","lease_status"]
        rows = [tuple(b.get(col) for col in columns) for b in blobs]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
