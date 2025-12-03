"""
Primary barcode decoding worker using ZBar.

Attempts to decode barcodes from preprocessed images using the ZBar library.
Falls back to Gemini if no barcodes are found.
"""

import time

import structlog

from src.barcode import BarcodeDecoder
from src.db import DetectionRepository, ImageRepository, ProductRepository, get_database
from src.models import (
    DetectionDoc,
    DetectionSource,
    ImageStatus,
)
from src.storage import BlobPaths, get_blob_client

logger = structlog.get_logger(__name__)


def process_preprocessed_images(batch_size: int = 10) -> int:
    """
    Process preprocessed images with primary decoder.

    Returns:
        Number of images processed
    """
    db = get_database()
    image_repo = ImageRepository(db)
    detection_repo = DetectionRepository(db)
    product_repo = ProductRepository(db)
    blob_client = get_blob_client()
    decoder = BarcodeDecoder(try_rotations=True)

    # Find preprocessed images
    preprocessed_images = image_repo.find_preprocessed(limit=batch_size)
    logger.info("Found preprocessed images", count=len(preprocessed_images))

    processed_count = 0

    for image_doc in preprocessed_images:
        try:
            # Idempotency check: skip if detections already exist
            if detection_repo.exists_for_image(image_doc.image_id):
                logger.info(
                    "Skipping image with existing detections",
                    image_id=image_doc.image_id,
                )
                continue

            logger.info(
                "Decoding image",
                image_id=image_doc.image_id,
                batch_id=image_doc.batch_id,
            )

            # Update status
            image_repo.update_status(image_doc.image_id, ImageStatus.DECODING_PRIMARY)

            # Get preprocessed image path
            preprocessed_path = image_doc.preprocessing.normalized_path
            if not preprocessed_path:
                preprocessed_path = BlobPaths.preprocessed(
                    image_doc.batch_id,
                    image_doc.image_id,
                )

            # Download preprocessed image
            start_time = time.time()
            image_data = blob_client.download_blob(preprocessed_path)

            # Decode barcodes
            results = decoder.decode(image_data)
            duration_ms = int((time.time() - start_time) * 1000)

            # Filter valid results
            valid_results = [r for r in results if r.is_valid]

            logger.info(
                "Decoding complete",
                image_id=image_doc.image_id,
                total_found=len(results),
                valid_found=len(valid_results),
                duration_ms=duration_ms,
            )

            # Record attempt
            image_doc.add_decoder_attempt(
                decoder="zbar",
                success=len(valid_results) > 0,
                is_fallback=False,
                codes_found=len(valid_results),
                duration_ms=duration_ms,
            )

            if valid_results:
                # Create detections
                detections = []
                for result in valid_results:
                    # Check product catalog
                    product = product_repo.get_by_any_code(result.code)

                    detection = DetectionDoc(
                        image_id=image_doc.image_id,
                        batch_id=image_doc.batch_id,
                        source_filename=image_doc.source_filename,
                        code=result.code,
                        symbology=result.symbology,
                        normalized_code=result.normalized_code,
                        source=DetectionSource.PRIMARY_ZBAR,
                        rotation_degrees=result.rotation,
                        checksum_valid=result.checksum_valid,
                        length_valid=result.length_valid,
                        numeric_only=result.numeric_only,
                        product_found=product is not None,
                        product_id=str(product.id) if product and product.id else None,
                    )
                    detections.append(detection)

                # Insert detections
                detection_repo.create_many(detections)

                # Update image
                dest_path = BlobPaths.processed(
                    image_doc.batch_id,
                    image_doc.image_id,
                )
                blob_client.move_blob(preprocessed_path, dest_path)

                image_repo.update(
                    image_doc.image_id,
                    {
                        "status": ImageStatus.DECODED_PRIMARY.value,
                        "final_blob_path": dest_path,
                        "detection_count": len(detections),
                        "processing": image_doc.processing.model_dump(),
                    },
                )

                logger.info(
                    "Image decoded successfully",
                    image_id=image_doc.image_id,
                    detections=len(detections),
                )

            else:
                # No valid barcodes found - mark for fallback
                image_repo.update(
                    image_doc.image_id,
                    {
                        "status": ImageStatus.PREPROCESSED.value,  # Keep as preprocessed
                        "processing.needs_fallback": True,
                        "processing.primary_attempts": [
                            a.model_dump() for a in image_doc.processing.primary_attempts
                        ],
                    },
                )

                logger.info(
                    "No barcodes found, marked for fallback",
                    image_id=image_doc.image_id,
                )

            processed_count += 1

        except Exception as e:
            logger.error(
                "Failed to decode image",
                image_id=image_doc.image_id,
                error=str(e),
            )
            image_repo.add_processing_error(
                image_doc.image_id,
                stage="decode_primary",
                message=str(e),
            )
            # Mark for fallback on error
            image_repo.update(
                image_doc.image_id,
                {
                    "status": ImageStatus.PREPROCESSED.value,
                    "processing.needs_fallback": True,
                },
            )

    return processed_count


def main():
    """Main entry point for primary decode worker."""
    import argparse

    parser = argparse.ArgumentParser(description="Primary Decode Worker")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of images per batch")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--daemon", action="store_true", help="Keep running even when no work (daemon mode)"
    )
    args = parser.parse_args()

    logger.info("Starting primary decode worker", batch_size=args.batch_size)

    consecutive_empty = 0  # Track consecutive empty polls

    while True:
        try:
            processed = process_preprocessed_images(args.batch_size)
            if processed > 0:
                logger.info("Batch complete", processed=processed)
                consecutive_empty = 0
            else:
                consecutive_empty += 1
        except Exception as e:
            logger.error("Worker error", error=str(e))

        if args.once:
            break

        # Exit when no work left (unless in daemon mode)
        if not args.daemon and consecutive_empty >= 2:
            logger.info("No more images to process, exiting")
            break

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
