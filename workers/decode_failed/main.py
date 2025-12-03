"""
Retry worker for failed barcode decoding using Google Gemini.

Processes images that previously failed Gemini decoding and retries,
leveraging Gemini's non-deterministic behavior to potentially get different results.
"""

import time

import structlog

from src.db import DetectionRepository, ImageRepository, ProductRepository, get_database
from src.llm import GeminiClient
from src.models import (
    DetectionDoc,
    DetectionSource,
    ImageStatus,
)
from src.storage import BlobPaths, get_blob_client

logger = structlog.get_logger(__name__)

# Maximum number of Gemini attempts (includes initial fallback + retries)
MAX_GEMINI_ATTEMPTS = 3


def process_failed_images(batch_size: int = 10) -> int:
    """
    Process failed images by retrying Gemini decoding.

    Returns:
        Number of images processed
    """
    db = get_database()
    image_repo = ImageRepository(db)
    detection_repo = DetectionRepository(db)
    product_repo = ProductRepository(db)
    blob_client = get_blob_client()

    # Initialize Gemini client
    try:
        gemini = GeminiClient()
    except ValueError as e:
        logger.error("Gemini client not configured", error=str(e))
        return 0

    # Find failed images eligible for retry
    failed_images = image_repo.find_failed_for_retry(
        limit=batch_size,
        max_attempts=MAX_GEMINI_ATTEMPTS,
    )
    logger.info("Found failed images for retry", count=len(failed_images))

    processed_count = 0

    for image_doc in failed_images:
        try:
            # Idempotency check: skip if detections already exist
            if detection_repo.exists_for_image(image_doc.image_id):
                logger.info(
                    "Skipping image with existing detections",
                    image_id=image_doc.image_id,
                )
                continue

            attempt_number = len(image_doc.processing.fallback_attempts) + 1
            logger.info(
                "Retrying with Gemini",
                image_id=image_doc.image_id,
                batch_id=image_doc.batch_id,
                attempt=attempt_number,
                max_attempts=MAX_GEMINI_ATTEMPTS,
            )

            # Update status to show we're retrying
            image_repo.update_status(image_doc.image_id, ImageStatus.DECODING_FALLBACK)

            # Get image path from failed folder
            image_path = image_doc.final_blob_path
            if not image_path:
                # Fallback to expected failed path
                image_path = BlobPaths.failed(
                    image_doc.batch_id,
                    image_doc.image_id,
                )

            # Download image
            start_time = time.time()
            image_data = blob_client.download_blob(image_path)

            # Call Gemini
            response = gemini.extract_barcodes(image_data)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.error:
                raise RuntimeError(f"Gemini error: {response.error}")

            # Filter valid results
            valid_results = [r for r in response.results if r.is_valid]

            logger.info(
                "Gemini retry complete",
                image_id=image_doc.image_id,
                attempt=attempt_number,
                total_found=len(response.results),
                valid_found=len(valid_results),
                duration_ms=duration_ms,
                tokens_used=response.tokens_used,
            )

            # Record attempt
            image_doc.add_decoder_attempt(
                decoder="gemini",
                success=len(valid_results) > 0,
                is_fallback=True,
                codes_found=len(valid_results),
                duration_ms=duration_ms,
            )

            # Update Gemini usage tracking
            if response.tokens_used:
                current_tokens = image_doc.processing.gemini_tokens_used or 0
                image_doc.processing.gemini_tokens_used = current_tokens + response.tokens_used

            if len(valid_results) == 0:
                # Still no valid barcodes - keep as failed
                # Image stays in failed/ folder
                image_repo.update(
                    image_doc.image_id,
                    {
                        "status": ImageStatus.FAILED.value,
                        "processing": image_doc.processing.model_dump(),
                    },
                )

                logger.info(
                    "Retry unsuccessful, still failed",
                    image_id=image_doc.image_id,
                    total_attempts=attempt_number,
                )

            elif len(valid_results) == 1:
                # Single valid barcode - success on retry!
                result = valid_results[0]
                product = product_repo.get_by_any_code(result.code)

                detection = DetectionDoc(
                    image_id=image_doc.image_id,
                    batch_id=image_doc.batch_id,
                    source_filename=image_doc.source_filename,
                    code=result.code,
                    symbology=result.validated_symbology,
                    source=DetectionSource.FALLBACK_GEMINI,
                    confidence=result.confidence,
                    checksum_valid=result.checksum_valid,
                    length_valid=True,
                    numeric_only=result.code.isdigit(),
                    gemini_confidence=result.confidence,
                    gemini_symbology_guess=result.symbology_guess,
                    product_found=product is not None,
                    product_id=str(product.id) if product and product.id else None,
                )
                detection_repo.create(detection)

                # Move from failed/ to processed/
                dest_path = BlobPaths.processed(
                    image_doc.batch_id,
                    image_doc.image_id,
                )
                blob_client.move_blob(image_path, dest_path)

                image_repo.update(
                    image_doc.image_id,
                    {
                        "status": ImageStatus.DECODED_FALLBACK.value,
                        "final_blob_path": dest_path,
                        "detection_count": 1,
                        "processing": image_doc.processing.model_dump(),
                    },
                )

                logger.info(
                    "Image decoded on retry!",
                    image_id=image_doc.image_id,
                    code=result.code,
                    attempt=attempt_number,
                )

            else:
                # Multiple valid barcodes - needs manual review
                detections = []
                for result in valid_results:
                    product = product_repo.get_by_any_code(result.code)

                    detection = DetectionDoc(
                        image_id=image_doc.image_id,
                        batch_id=image_doc.batch_id,
                        source_filename=image_doc.source_filename,
                        code=result.code,
                        symbology=result.validated_symbology,
                        source=DetectionSource.FALLBACK_GEMINI,
                        confidence=result.confidence,
                        checksum_valid=result.checksum_valid,
                        length_valid=True,
                        numeric_only=result.code.isdigit(),
                        gemini_confidence=result.confidence,
                        gemini_symbology_guess=result.symbology_guess,
                        ambiguous=True,  # Mark as ambiguous
                        product_found=product is not None,
                        product_id=str(product.id) if product and product.id else None,
                    )
                    detections.append(detection)

                detection_repo.create_many(detections)

                # Move from failed/ to manual-review/
                dest_path = BlobPaths.manual_review(
                    image_doc.batch_id,
                    image_doc.image_id,
                )
                blob_client.move_blob(image_path, dest_path)

                image_repo.update(
                    image_doc.image_id,
                    {
                        "status": ImageStatus.MANUAL_REVIEW.value,
                        "final_blob_path": dest_path,
                        "detection_count": len(detections),
                        "processing": image_doc.processing.model_dump(),
                    },
                )

                logger.info(
                    "Multiple barcodes found on retry, needs manual review",
                    image_id=image_doc.image_id,
                    detections=len(detections),
                    attempt=attempt_number,
                )

            processed_count += 1

        except Exception as e:
            logger.error(
                "Failed to retry with Gemini",
                image_id=image_doc.image_id,
                error=str(e),
            )
            image_repo.add_processing_error(
                image_doc.image_id,
                stage="decode_failed",
                message=str(e),
            )

            # Keep image in failed state and location
            image_repo.update_status(image_doc.image_id, ImageStatus.FAILED)

    return processed_count


def main():
    """Main entry point for failed decode retry worker."""
    import argparse

    parser = argparse.ArgumentParser(description="Failed Decode Retry Worker (Gemini)")
    parser.add_argument("--batch-size", type=int, default=5, help="Number of images per batch")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--daemon", action="store_true", help="Keep running even when no work (daemon mode)"
    )
    args = parser.parse_args()

    logger.info(
        "Starting failed decode retry worker",
        batch_size=args.batch_size,
        max_attempts=MAX_GEMINI_ATTEMPTS,
    )

    consecutive_empty = 0  # Track consecutive empty polls

    while True:
        try:
            processed = process_failed_images(args.batch_size)
            if processed > 0:
                logger.info("Batch complete", processed=processed)
                consecutive_empty = 0  # Reset counter
            else:
                consecutive_empty += 1
        except Exception as e:
            logger.error("Worker error", error=str(e))

        if args.once:
            break

        # Exit when no work left (unless in daemon mode)
        if not args.daemon and consecutive_empty >= 2:
            logger.info("No more images to retry, exiting")
            break

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
