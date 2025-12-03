"""
Azure Blob Storage client wrapper.
"""

from functools import lru_cache
from io import BytesIO
from typing import BinaryIO

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from src.config import get_settings


class BlobStorageClient:
    """
    Client for Azure Blob Storage operations.

    Supports both connection string and Managed Identity authentication.
    """

    def __init__(
        self,
        connection_string: str | None = None,
        account_url: str | None = None,
        container_name: str = "product-images",
    ):
        self.container_name = container_name

        if connection_string:
            self.service_client = BlobServiceClient.from_connection_string(connection_string)
        elif account_url:
            # Use Managed Identity
            credential = DefaultAzureCredential()
            self.service_client = BlobServiceClient(account_url, credential=credential)
        else:
            raise ValueError("Either connection_string or account_url must be provided")

        self.container_client = self.service_client.get_container_client(container_name)

    def ensure_container_exists(self) -> None:
        """Create container if it doesn't exist."""
        if not self.container_client.exists():
            self.container_client.create_container()

    def upload_blob(
        self,
        path: str,
        data: bytes | BinaryIO,
        content_type: str = "image/jpeg",
        overwrite: bool = True,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """
        Upload data to a blob.

        Args:
            path: Blob path within container (e.g., "incoming/batch1/img.jpg")
            data: Bytes or file-like object to upload
            content_type: MIME type of the content
            overwrite: Whether to overwrite existing blob
            metadata: Optional metadata dictionary

        Returns:
            Full blob URL
        """
        blob_client = self.container_client.get_blob_client(path)

        from azure.storage.blob import ContentSettings

        content_settings = ContentSettings(content_type=content_type)

        blob_client.upload_blob(
            data,
            overwrite=overwrite,
            content_settings=content_settings,
            metadata=metadata,
        )

        return blob_client.url

    def download_blob(self, path: str) -> bytes:
        """
        Download blob content as bytes.

        Args:
            path: Blob path within container

        Returns:
            Blob content as bytes
        """
        blob_client = self.container_client.get_blob_client(path)
        download_stream = blob_client.download_blob()
        return download_stream.readall()

    def download_blob_to_stream(self, path: str) -> BytesIO:
        """
        Download blob content to a BytesIO stream.

        Args:
            path: Blob path within container

        Returns:
            BytesIO containing blob data
        """
        data = self.download_blob(path)
        return BytesIO(data)

    def blob_exists(self, path: str) -> bool:
        """Check if a blob exists."""
        blob_client = self.container_client.get_blob_client(path)
        return blob_client.exists()

    def delete_blob(self, path: str) -> bool:
        """
        Delete a blob.

        Returns:
            True if deleted, False if didn't exist
        """
        blob_client = self.container_client.get_blob_client(path)
        if blob_client.exists():
            blob_client.delete_blob()
            return True
        return False

    def copy_blob(
        self,
        source_path: str,
        dest_path: str,
        delete_source: bool = False,
    ) -> str:
        """
        Copy blob to a new location.

        Args:
            source_path: Source blob path
            dest_path: Destination blob path
            delete_source: If True, delete source after copy (move)

        Returns:
            Destination blob URL
        """
        source_blob = self.container_client.get_blob_client(source_path)
        dest_blob = self.container_client.get_blob_client(dest_path)

        # Copy from source
        dest_blob.start_copy_from_url(source_blob.url)

        # Wait for copy to complete
        props = dest_blob.get_blob_properties()
        while props.copy.status == "pending":
            import time

            time.sleep(0.5)
            props = dest_blob.get_blob_properties()

        if props.copy.status != "success":
            raise RuntimeError(f"Blob copy failed: {props.copy.status}")

        if delete_source:
            source_blob.delete_blob()

        return dest_blob.url

    def move_blob(self, source_path: str, dest_path: str) -> str:
        """
        Move blob to a new location (copy + delete).

        Args:
            source_path: Source blob path
            dest_path: Destination blob path

        Returns:
            Destination blob URL
        """
        return self.copy_blob(source_path, dest_path, delete_source=True)

    def list_blobs(
        self,
        prefix: str | None = None,
        max_results: int | None = None,
    ) -> list[str]:
        """
        List blob paths with optional prefix filter.

        Args:
            prefix: Prefix to filter blobs (e.g., "incoming/batch1/")
            max_results: Maximum number of results to return

        Returns:
            List of blob paths
        """
        blobs = self.container_client.list_blobs(name_starts_with=prefix)

        paths = []
        for blob in blobs:
            paths.append(blob.name)
            if max_results and len(paths) >= max_results:
                break

        return paths

    def get_blob_properties(self, path: str) -> dict:
        """Get blob properties and metadata."""
        blob_client = self.container_client.get_blob_client(path)
        props = blob_client.get_blob_properties()
        return {
            "name": props.name,
            "size": props.size,
            "content_type": props.content_settings.content_type,
            "last_modified": props.last_modified,
            "etag": props.etag,
            "metadata": props.metadata,
        }

    def get_blob_url(self, path: str) -> str:
        """Get the URL for a blob."""
        blob_client = self.container_client.get_blob_client(path)
        return blob_client.url

    def generate_sas_url(
        self,
        path: str,
        expiry_hours: int = 1,
        read_only: bool = True,
    ) -> str:
        """
        Generate a SAS URL for blob access.

        Args:
            path: Blob path
            expiry_hours: Hours until SAS expires
            read_only: If True, only allow read access

        Returns:
            SAS URL for blob
        """
        from datetime import datetime, timedelta

        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        blob_client = self.container_client.get_blob_client(path)

        # Get account key from connection string if available
        settings = get_settings()
        if not settings.azure_connection_string_str:
            raise ValueError("SAS generation requires connection string")

        # Parse account key from connection string
        conn_parts = dict(
            part.split("=", 1)
            for part in settings.azure_connection_string_str.split(";")
            if "=" in part
        )
        account_name = conn_parts.get("AccountName", "")
        account_key = conn_parts.get("AccountKey", "")

        permissions = BlobSasPermissions(read=True)
        if not read_only:
            permissions = BlobSasPermissions(read=True, write=True, delete=True)

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self.container_name,
            blob_name=path,
            account_key=account_key,
            permission=permissions,
            expiry=datetime.utcnow() + timedelta(hours=expiry_hours),
        )

        return f"{blob_client.url}?{sas_token}"


@lru_cache
def get_blob_client() -> BlobStorageClient:
    """Get cached blob storage client."""
    settings = get_settings()
    return BlobStorageClient(
        connection_string=settings.azure_connection_string_str,
        account_url=settings.azure_storage_account_url,
        container_name=settings.azure_storage_container,
    )
