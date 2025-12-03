"""
Image preprocessing worker.

Normalizes images for barcode detection:
- Converts to grayscale
- Resizes to max dimension
- Applies denoising
- Applies CLAHE (Contrast Limited Adaptive Histogram Equalization)
"""

import time
from dataclasses import dataclass

import cv2
import numpy as np
import structlog

from src.config import get_settings
from src.db import ImageRepository, get_database
from src.models import ImageStatus, PreprocessingInfo
from src.storage import BlobPaths, get_blob_client

logger = structlog.get_logger(__name__)


@dataclass
class PreprocessConfig:
    """Configuration for image preprocessing."""

    max_dimension: int = 2048
    denoise_strength: int = 10
    apply_clahe: bool = True
    clahe_clip_limit: float = 2.0
    clahe_tile_size: tuple[int, int] = (8, 8)
    output_format: str = "JPEG"
    jpeg_quality: int = 90


class ImagePreprocessor:
    """
    Preprocesses images for optimal barcode detection.
    """

    def __init__(self, config: PreprocessConfig | None = None):
        self.config = config or PreprocessConfig()
        settings = get_settings()
        self.config.max_dimension = settings.preprocess_max_dimension
        self.config.denoise_strength = settings.preprocess_denoise_strength

    def preprocess(self, image_data: bytes) -> tuple[bytes, PreprocessingInfo]:
        """
        Preprocess an image for barcode detection.

        Args:
            image_data: Raw image bytes

        Returns:
            Tuple of (processed_bytes, preprocessing_info)
        """
        start_time = time.time()

        # Load image
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Failed to decode image")

        original_height, original_width = img.shape[:2]

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Resize if needed
        processed_width, processed_height = original_width, original_height
        if max(original_width, original_height) > self.config.max_dimension:
            scale = self.config.max_dimension / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_AREA)
            processed_width, processed_height = new_width, new_height

        # Apply denoising
        denoised = gray
        if self.config.denoise_strength > 0:
            denoised = cv2.fastNlMeansDenoising(
                gray,
                None,
                h=self.config.denoise_strength,
                templateWindowSize=7,
                searchWindowSize=21,
            )

        # Apply CLAHE
        clahe_applied = False
        final = denoised
        if self.config.apply_clahe:
            clahe = cv2.createCLAHE(
                clipLimit=self.config.clahe_clip_limit,
                tileGridSize=self.config.clahe_tile_size,
            )
            final = clahe.apply(denoised)
            clahe_applied = True

        # Encode to JPEG
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality]
        _, encoded = cv2.imencode(".jpg", final, encode_params)
        processed_bytes = encoded.tobytes()

        duration_ms = int((time.time() - start_time) * 1000)

        info = PreprocessingInfo(
            original_width=original_width,
            original_height=original_height,
            processed_width=processed_width,
            processed_height=processed_height,
            grayscale=True,
            clahe_applied=clahe_applied,
            denoised=self.config.denoise_strength > 0,
            duration_ms=duration_ms,
        )

        return processed_bytes, info


def process_pending_images(batch_size: int = 10) -> int:
    """
    Process pending images.

    Returns:
        Number of images processed
    """
    db = get_database()
    image_repo = ImageRepository(db)
    blob_client = get_blob_client()
    preprocessor = ImagePreprocessor()

    # Find pending images
    pending_images = image_repo.find_pending(limit=batch_size)
    logger.info("Found pending images", count=len(pending_images))

    processed_count = 0

    for image_doc in pending_images:
        try:
            # Idempotency check: skip if already preprocessed
            if image_doc.preprocessing.normalized_path:
                logger.info(
                    "Skipping already preprocessed image",
                    image_id=image_doc.image_id,
                )
                continue

            logger.info(
                "Processing image",
                image_id=image_doc.image_id,
                batch_id=image_doc.batch_id,
            )

            # Update status to preprocessing
            image_repo.update_status(image_doc.image_id, ImageStatus.PREPROCESSING)

            # Download from blob storage
            source_data = blob_client.download_blob(image_doc.source_path)

            # Preprocess
            processed_data, prep_info = preprocessor.preprocess(source_data)

            # Upload preprocessed image
            dest_path = BlobPaths.preprocessed(
                image_doc.batch_id,
                image_doc.image_id,
            )
            blob_client.upload_blob(dest_path, processed_data)

            # Update preprocessing info
            prep_info.normalized_path = dest_path
            from src.models.base import utc_now

            prep_info.completed_at = utc_now()

            # Move incoming to archived (keeps original for debugging/reprocessing)
            archived_path = BlobPaths.archived(
                image_doc.batch_id,
                image_doc.image_id,
                BlobPaths.get_extension(image_doc.source_path),
            )
            try:
                blob_client.move_blob(image_doc.source_path, archived_path)
                logger.debug(
                    "Moved incoming to archived",
                    source=image_doc.source_path,
                    dest=archived_path,
                )
            except Exception as move_err:
                # Non-fatal - log but continue
                logger.warning(
                    "Failed to archive incoming image",
                    image_id=image_doc.image_id,
                    error=str(move_err),
                )
                archived_path = image_doc.source_path  # Keep original path if move fails

            # Update document
            image_repo.update(
                image_doc.image_id,
                {
                    "preprocessing": prep_info.model_dump(),
                    "status": ImageStatus.PREPROCESSED.value,
                    "status_updated_at": utc_now(),
                },
            )

            processed_count += 1
            logger.info(
                "Image preprocessed",
                image_id=image_doc.image_id,
                duration_ms=prep_info.duration_ms,
            )

        except Exception as e:
            logger.error(
                "Failed to preprocess image",
                image_id=image_doc.image_id,
                error=str(e),
            )
            image_repo.add_processing_error(
                image_doc.image_id,
                stage="preprocess",
                message=str(e),
            )
            image_repo.update_status(image_doc.image_id, ImageStatus.FAILED)

    return processed_count


def main():
    """Main entry point for preprocessing worker."""
    import argparse

    parser = argparse.ArgumentParser(description="Preprocessing Worker")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of images per batch")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between polls")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--daemon", action="store_true", help="Keep running even when no work (daemon mode)"
    )
    args = parser.parse_args()

    logger.info("Starting preprocessing worker", batch_size=args.batch_size)

    consecutive_empty = 0  # Track consecutive empty polls

    while True:
        try:
            processed = process_pending_images(args.batch_size)
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
