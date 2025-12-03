"""
Blob path utilities for consistent path generation.
"""


class BlobPaths:
    """
    Standardized blob path generation.

    Container structure:
    - incoming/{batch_id}/{image_id}.jpg      -> Raw uploads (temporary)
    - archived/{batch_id}/{image_id}.jpg      -> Moved from incoming after preprocessing
    - preprocessed/{batch_id}/{image_id}_norm.jpg
    - processed/{batch_id}/{image_id}.jpg
    - failed/{batch_id}/{image_id}.jpg
    - manual-review/{batch_id}/{image_id}.jpg
    """

    INCOMING = "incoming"
    ARCHIVED = "archived"
    PREPROCESSED = "preprocessed"
    PROCESSED = "processed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual-review"

    @staticmethod
    def incoming(batch_id: str, image_id: str, extension: str = "jpg") -> str:
        """Path for incoming (raw) images."""
        return f"{BlobPaths.INCOMING}/{batch_id}/{image_id}.{extension}"

    @staticmethod
    def archived(batch_id: str, image_id: str, extension: str = "jpg") -> str:
        """Path for archived images (moved from incoming after preprocessing)."""
        return f"{BlobPaths.ARCHIVED}/{batch_id}/{image_id}.{extension}"

    @staticmethod
    def preprocessed(batch_id: str, image_id: str, extension: str = "jpg") -> str:
        """Path for preprocessed (normalized) images."""
        return f"{BlobPaths.PREPROCESSED}/{batch_id}/{image_id}_norm.{extension}"

    @staticmethod
    def processed(batch_id: str, image_id: str, extension: str = "jpg") -> str:
        """Path for successfully processed images."""
        return f"{BlobPaths.PROCESSED}/{batch_id}/{image_id}.{extension}"

    @staticmethod
    def failed(batch_id: str, image_id: str, extension: str = "jpg") -> str:
        """Path for failed images."""
        return f"{BlobPaths.FAILED}/{batch_id}/{image_id}.{extension}"

    @staticmethod
    def manual_review(batch_id: str, image_id: str, extension: str = "jpg") -> str:
        """Path for images requiring manual review."""
        return f"{BlobPaths.MANUAL_REVIEW}/{batch_id}/{image_id}.{extension}"

    @staticmethod
    def extract_batch_and_image_id(path: str) -> tuple[str, str]:
        """
        Extract batch_id and image_id from a blob path.

        Args:
            path: Full blob path like "incoming/batch1/abc123.jpg"

        Returns:
            Tuple of (batch_id, image_id)
        """
        parts = path.split("/")
        if len(parts) < 3:
            raise ValueError(f"Invalid blob path format: {path}")

        batch_id = parts[1]
        filename = parts[2]
        # Remove extension and _norm suffix if present
        image_id = filename.rsplit(".", 1)[0]
        image_id = image_id.removesuffix("_norm")

        return batch_id, image_id

    @staticmethod
    def get_folder(path: str) -> str:
        """Get the folder (first component) from a path."""
        return path.split("/")[0]

    @staticmethod
    def get_extension(path: str) -> str:
        """Get file extension from path."""
        return path.rsplit(".", 1)[-1] if "." in path else ""

    @staticmethod
    def change_folder(path: str, new_folder: str) -> str:
        """
        Change the folder component of a path.

        Args:
            path: Original path like "incoming/batch1/img.jpg"
            new_folder: New folder like "processed"

        Returns:
            New path like "processed/batch1/img.jpg"
        """
        parts = path.split("/", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid path format: {path}")
        return f"{new_folder}/{parts[1]}"
