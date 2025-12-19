"""
Image upload CLI tool.

Uploads local images to Azure Blob Storage and creates corresponding
database records for processing.

Usage:
    poetry run upload --batch-id batch_001 --source ./images/
    poetry run upload --batch-id batch_001 --source ./images/ --prefix STORE01_
"""

import uuid
from pathlib import Path

import click
import structlog

from src.db import ImageRepository, get_database
from src.models import ImageDoc, ImageStatus
from src.storage import BlobPaths, get_blob_client

logger = structlog.get_logger(__name__)

# Supported image extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def get_content_type(extension: str) -> str:
    """Get MIME type from file extension."""
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    return mapping.get(extension.lower(), "application/octet-stream")


def find_images(source_dir: Path) -> list[Path]:
    """Find all supported image files in a directory."""
    images = []
    for ext in SUPPORTED_EXTENSIONS:
        images.extend(source_dir.glob(f"*{ext}"))
        images.extend(source_dir.glob(f"*{ext.upper()}"))
    return sorted(images)


def upload_image(
    file_path: Path,
    batch_id: str,
    image_id: str,
    blob_client,
    image_repo: ImageRepository,
    prefix: str = "",
    external_id: str | None = None,
) -> bool:
    """
    Upload a single image.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read file
        with open(file_path, "rb") as f:
            data = f.read()

        # Determine content type
        extension = file_path.suffix.lower()
        content_type = get_content_type(extension)

        # Create blob path
        blob_path = BlobPaths.incoming(batch_id, image_id, extension.lstrip("."))

        # Upload to blob storage
        blob_client.upload_blob(
            path=blob_path,
            data=data,
            content_type=content_type,
            metadata={
                "batch_id": batch_id,
                "image_id": image_id,
                "original_filename": file_path.name,
            },
        )

        # Create database record
        image_doc = ImageDoc(
            image_id=image_id,
            batch_id=batch_id,
            source_path=blob_path,
            source_filename=file_path.name,
            external_id=external_id or f"{prefix}{file_path.stem}",
            status=ImageStatus.PENDING,
            content_type=content_type,
            file_size_bytes=len(data),
        )

        image_repo.create(image_doc)

        return True

    except Exception as e:
        logger.error(
            "Failed to upload image",
            file=str(file_path),
            error=str(e),
        )
        return False


@click.command()
@click.option(
    "--batch-id",
    required=True,
    help="Batch identifier for this upload session",
)
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Source directory containing images",
)
@click.option(
    "--prefix",
    default="",
    help="Prefix for external IDs",
)
@click.option(
    "--recursive",
    is_flag=True,
    help="Recursively search for images in subdirectories",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be uploaded without uploading",
)
@click.option(
    "--skip-duplicates/--allow-duplicates",
    default=True,
    help="Skip files that already exist in this batch (default: skip)",
)
def main(
    batch_id: str,
    source: Path,
    prefix: str,
    recursive: bool,
    dry_run: bool,
    skip_duplicates: bool,
):
    """Upload product images for barcode extraction."""
    click.echo("EAN Extraction - Image Upload Tool")
    click.echo(f"Batch ID: {batch_id}")
    click.echo(f"Source: {source}")
    click.echo("")

    # Find images
    if recursive:
        images = []
        for ext in SUPPORTED_EXTENSIONS:
            images.extend(source.rglob(f"*{ext}"))
            images.extend(source.rglob(f"*{ext.upper()}"))
        images = sorted(images)
    else:
        images = find_images(source)

    if not images:
        click.echo("No images found in the specified directory.")
        return

    click.echo(f"Found {len(images)} images")

    if dry_run:
        click.echo("\n[DRY RUN] Would upload:")
        for img in images[:10]:
            click.echo(f"  - {img.name}")
        if len(images) > 10:
            click.echo(f"  ... and {len(images) - 10} more")
        return

    # Initialize clients
    try:
        blob_client = get_blob_client()
        blob_client.ensure_container_exists()
        db = get_database()
        image_repo = ImageRepository(db)
    except Exception as e:
        click.echo(f"Error: Failed to initialize clients: {e}", err=True)
        return

    # Upload images
    success_count = 0
    fail_count = 0
    skipped_count = 0

    with click.progressbar(images, label="Uploading images") as progress:
        for file_path in progress:
            # Check for duplicates
            if skip_duplicates:
                existing = image_repo.get_by_source_filename(batch_id, file_path.name)
                if existing:
                    skipped_count += 1
                    logger.debug(
                        "Skipping duplicate",
                        filename=file_path.name,
                        existing_image_id=existing.image_id,
                    )
                    continue

            image_id = str(uuid.uuid4())

            if upload_image(
                file_path=file_path,
                batch_id=batch_id,
                image_id=image_id,
                blob_client=blob_client,
                image_repo=image_repo,
                prefix=prefix,
            ):
                success_count += 1
            else:
                fail_count += 1

    click.echo("")
    click.echo("Upload complete!")
    click.echo(f"  Successful: {success_count}")
    click.echo(f"  Skipped (duplicates): {skipped_count}")
    click.echo(f"  Failed: {fail_count}")

    if success_count > 0:
        click.echo(f"\nImages are now queued for processing under batch '{batch_id}'")
        click.echo("Run the workers to start processing:")
        click.echo("  poetry run python -m workers.preprocess.main")


if __name__ == "__main__":
    main()
