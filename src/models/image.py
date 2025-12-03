"""
Image document model for tracking uploaded images through the processing pipeline.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.models.base import MongoBaseModel, utc_now


class ImageStatus(str, Enum):
    """Status of an image in the processing pipeline."""

    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    PREPROCESSED = "preprocessed"
    DECODING_PRIMARY = "decoding_primary"
    DECODED_PRIMARY = "decoded_primary"
    DECODING_FALLBACK = "decoding_fallback"
    DECODED_FALLBACK = "decoded_fallback"
    MANUAL_REVIEW = "manual_review"
    DECODED_MANUAL = "decoded_manual"
    FAILED = "failed"


class PreprocessingInfo(BaseModel):
    """Information about image preprocessing."""

    normalized_path: str | None = Field(None, description="Path to normalized image in blob storage")
    original_width: int | None = None
    original_height: int | None = None
    processed_width: int | None = None
    processed_height: int | None = None
    grayscale: bool = False
    clahe_applied: bool = False
    denoised: bool = False
    rotations_generated: list[int] = Field(default_factory=list)
    duration_ms: int | None = None
    completed_at: datetime | None = None


class ProcessingError(BaseModel):
    """Error that occurred during processing."""

    stage: str
    message: str
    timestamp: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] | None = None


class DecoderAttempt(BaseModel):
    """Record of a decoding attempt."""

    decoder: str  # "zbar", "zxing", "gemini"
    attempt_number: int
    success: bool
    codes_found: int = 0
    duration_ms: int | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    error: str | None = None


class ProcessingInfo(BaseModel):
    """Information about the decoding process."""

    primary_attempts: list[DecoderAttempt] = Field(default_factory=list)
    fallback_attempts: list[DecoderAttempt] = Field(default_factory=list)
    needs_fallback: bool = False
    gemini_tokens_used: int | None = None
    errors: list[ProcessingError] = Field(default_factory=list)


class ImageDoc(MongoBaseModel):
    """
    MongoDB document for tracking an image through the processing pipeline.

    Collection: images
    """

    # Core identifiers
    image_id: str = Field(..., description="Unique image identifier (UUID)")
    batch_id: str = Field(..., description="Batch this image belongs to")

    # Source information
    source_path: str = Field(..., description="Original blob path in incoming/")
    source_filename: str | None = Field(None, description="Original filename")
    external_id: str | None = Field(None, description="External system reference")

    # Status tracking
    status: ImageStatus = Field(default=ImageStatus.PENDING)
    status_updated_at: datetime = Field(default_factory=utc_now)

    # Processing info
    preprocessing: PreprocessingInfo = Field(default_factory=PreprocessingInfo)
    processing: ProcessingInfo = Field(default_factory=ProcessingInfo)

    # Results
    final_blob_path: str | None = Field(None, description="Final location after processing")
    detection_count: int = Field(0, description="Number of barcodes detected")

    # Metadata
    content_type: str = Field(default="image/jpeg")
    file_size_bytes: int | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def update_status(self, new_status: ImageStatus) -> None:
        """Update status with timestamp."""
        self.status = new_status
        self.status_updated_at = utc_now()
        self.updated_at = utc_now()

    def add_error(self, stage: str, message: str, details: dict[str, Any] | None = None) -> None:
        """Add a processing error."""
        error = ProcessingError(stage=stage, message=message, details=details)
        self.processing.errors.append(error)
        self.updated_at = utc_now()

    def add_decoder_attempt(
        self,
        decoder: str,
        success: bool,
        is_fallback: bool = False,
        codes_found: int = 0,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """Record a decoding attempt."""
        attempts = self.processing.fallback_attempts if is_fallback else self.processing.primary_attempts
        attempt = DecoderAttempt(
            decoder=decoder,
            attempt_number=len(attempts) + 1,
            success=success,
            codes_found=codes_found,
            duration_ms=duration_ms,
            error=error,
        )
        attempts.append(attempt)
        self.updated_at = utc_now()
