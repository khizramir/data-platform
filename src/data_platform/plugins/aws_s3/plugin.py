"""AWS S3 plugin for the data integration platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata, QueryResult


class AWSS3Plugin(DataSourcePlugin):
    """Extracts object metadata from AWS S3 via the boto3 S3 client."""

    _METADATA = PluginMetadata(
        name="aws_s3", version="1.0.0",
        description="Extracts object metadata from AWS S3",
        author="Data Platform", supported_schemes=["s3", "s3a"],
    )

    def __init__(self) -> None:
        """Initialize AWS S3 plugin."""
        self._config: dict[str, Any] = {}
        self._client: Any = None
        self._connected: bool = False

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return self._METADATA

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate config. Requires 'bucket'.

        Args:
            config: Configuration dictionary.

        Raises:
            ValueError: If 'bucket' is missing.
        """
        if "bucket" not in config:
            raise ValueError("Config missing required key: 'bucket'")

    def connect(self, config: dict[str, Any]) -> None:
        """Build S3 client."""
        self.validate_config(config)
        self._config = config
        self._client = self._build_client(config)
        self._connected = True

    def disconnect(self) -> None:
        """Release the S3 client."""
        self._connected = False
        self._client = None
        self._config = {}

    def is_connected(self) -> bool:
        """Return True if an S3 client is available."""
        return self._connected and self._client is not None

    def fetch_data(self, query: str = "", params: Any = None) -> QueryResult:
        """List all objects in the configured S3 bucket/prefix."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        bucket = self._config["bucket"]
        prefix = query or self._config.get("prefix", "")
        objects = self._list_objects(bucket, prefix)
        return self._objects_to_result(objects, query=f"s3://{bucket}/{prefix}")

    def fetch_incremental(self, since: datetime, prefix: str = "") -> QueryResult:
        """Fetch objects modified after a given timestamp."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        bucket = self._config["bucket"]
        effective_prefix = prefix or self._config.get("prefix", "")
        all_objects = self._list_objects(bucket, effective_prefix)
        filtered = [obj for obj in all_objects
                    if obj.get("LastModified") and obj["LastModified"].replace(tzinfo=None) > since.replace(tzinfo=None)]
        return self._objects_to_result(filtered, query=f"s3://{bucket}/{effective_prefix}?since={since.isoformat()}")

    def discover_schema(self, prefix: str = "") -> dict[str, Any]:
        """Discover bucket structure and file extension distribution."""
        if not self.is_connected():
            raise RuntimeError("Plugin is not connected")
        bucket = self._config["bucket"]
        effective_prefix = prefix or self._config.get("prefix", "")
        common_prefixes = self._list_common_prefixes(bucket, effective_prefix)
        objects = self._list_objects(bucket, effective_prefix)
        ext_counts: dict[str, int] = {}
        for obj in objects:
            key = obj.get("Key", "")
            ext = key.rsplit(".", 1)[-1].lower() if "." in key.split("/")[-1] else "no_ext"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
        return {"bucket": bucket, "prefix": effective_prefix, "total_objects": len(objects),
                "common_prefixes": common_prefixes, "extensions": ext_counts,
                "columns": ["Key","Size","LastModified","ETag","StorageClass","Owner"]}

    def test_connection(self, config: dict[str, Any]) -> bool:
        """Test S3 connectivity via head_bucket."""
        try:
            self.validate_config(config)
            self._build_client(config).head_bucket(Bucket=config["bucket"])
            return True
        except Exception:
            return False

    def _build_client(self, config: dict[str, Any]) -> Any:
        """Build boto3 S3 client."""
        if "_client_stub" in config:
            return config["_client_stub"]
        try:
            import boto3  # type: ignore[import]
            kwargs: dict[str, Any] = {"region_name": config.get("region", "us-east-1")}
            if "aws_access_key_id" in config:
                kwargs["aws_access_key_id"] = config["aws_access_key_id"]
                kwargs["aws_secret_access_key"] = config["aws_secret_access_key"]
            return boto3.client("s3", **kwargs)
        except ImportError:
            raise RuntimeError("boto3 package is required for the AWS S3 plugin")

    def _list_objects(self, bucket: str, prefix: str) -> list[dict[str, Any]]:
        """List all objects with pagination."""
        objects: list[dict[str, Any]] = []
        paginator = self._client.get_paginator("list_objects_v2")
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix
        for page in paginator.paginate(**kwargs):
            objects.extend(page.get("Contents", []))
        return objects

    def _list_common_prefixes(self, bucket: str, prefix: str) -> list[str]:
        """List common prefixes (virtual directories)."""
        paginator = self._client.get_paginator("list_objects_v2")
        kwargs: dict[str, Any] = {"Bucket": bucket, "Delimiter": "/"}
        if prefix:
            kwargs["Prefix"] = prefix
        prefixes: list[str] = []
        for page in paginator.paginate(**kwargs):
            for cp in page.get("CommonPrefixes", []):
                prefixes.append(cp.get("Prefix", ""))
        return prefixes

    def _objects_to_result(self, objects: list[dict[str, Any]], query: str) -> QueryResult:
        """Convert S3 object list to QueryResult."""
        columns = ["Key","Size","LastModified","ETag","StorageClass","Owner"]
        rows = []
        for obj in objects:
            owner = obj.get("Owner", {})
            rows.append((obj.get("Key"), obj.get("Size"), obj.get("LastModified"),
                         obj.get("ETag"), obj.get("StorageClass"),
                         owner.get("DisplayName") if isinstance(owner, dict) else owner))
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), query=query)
