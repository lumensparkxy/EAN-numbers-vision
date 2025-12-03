"""
Tests for MongoDB models.
"""

import pytest
from datetime import datetime, timezone

from src.models import (
    ImageDoc,
    ImageStatus,
    DetectionDoc,
    DetectionSource,
    ProductDoc,
    JobDoc,
    JobStatus,
    JobType,
)
from src.models.detection import BarcodeSymbology


class TestImageDoc:
    """Tests for ImageDoc model."""

    def test_create_image_doc(self):
        """Test creating an ImageDoc."""
        image = ImageDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_path="incoming/batch-001/test-123.jpg",
        )

        assert image.image_id == "test-123"
        assert image.batch_id == "batch-001"
        assert image.status == ImageStatus.PENDING
        assert image.detection_count == 0

    def test_update_status(self):
        """Test updating image status."""
        image = ImageDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_path="incoming/batch-001/test-123.jpg",
        )

        original_updated = image.updated_at
        image.update_status(ImageStatus.PREPROCESSED)

        assert image.status == ImageStatus.PREPROCESSED
        assert image.updated_at >= original_updated

    def test_add_error(self):
        """Test adding processing error."""
        image = ImageDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_path="incoming/batch-001/test-123.jpg",
        )

        image.add_error("preprocess", "Test error", {"detail": "value"})

        assert len(image.processing.errors) == 1
        assert image.processing.errors[0].stage == "preprocess"
        assert image.processing.errors[0].message == "Test error"

    def test_add_decoder_attempt(self):
        """Test recording decoder attempts."""
        image = ImageDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_path="incoming/batch-001/test-123.jpg",
        )

        image.add_decoder_attempt(
            decoder="zbar",
            success=True,
            codes_found=2,
            duration_ms=150,
        )

        assert len(image.processing.primary_attempts) == 1
        assert image.processing.primary_attempts[0].decoder == "zbar"
        assert image.processing.primary_attempts[0].success is True

    def test_to_mongo(self):
        """Test conversion to MongoDB document."""
        image = ImageDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_path="incoming/batch-001/test-123.jpg",
        )

        doc = image.to_mongo()
        assert isinstance(doc, dict)
        assert doc["image_id"] == "test-123"
        assert doc["status"] == "pending"


class TestDetectionDoc:
    """Tests for DetectionDoc model."""

    def test_create_detection(self):
        """Test creating a detection."""
        detection = DetectionDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_filename="product_barcode.jpg",
            code="4006381333931",
            symbology=BarcodeSymbology.EAN_13,
            source=DetectionSource.PRIMARY_ZBAR,
            checksum_valid=True,
            length_valid=True,
            numeric_only=True,
        )

        assert detection.code == "4006381333931"
        assert detection.symbology == BarcodeSymbology.EAN_13
        assert detection.checksum_valid is True
        assert detection.source_filename == "product_barcode.jpg"

    def test_mark_chosen(self):
        """Test marking detection as chosen."""
        detection = DetectionDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_filename="ambiguous_barcode.jpg",
            code="4006381333931",
            source=DetectionSource.FALLBACK_GEMINI,
            ambiguous=True,
        )

        detection.mark_chosen("reviewer_1")

        assert detection.chosen is True
        assert detection.ambiguous is False
        assert detection.reviewed_by == "reviewer_1"
        assert detection.reviewed_at is not None

    def test_mark_rejected(self):
        """Test marking detection as rejected."""
        detection = DetectionDoc(
            image_id="test-123",
            batch_id="batch-001",
            source_filename="rejected_barcode.jpg",
            code="4006381333931",
            source=DetectionSource.FALLBACK_GEMINI,
        )

        detection.mark_rejected("reviewer_1")

        assert detection.rejected is True
        assert detection.reviewed_by == "reviewer_1"


class TestProductDoc:
    """Tests for ProductDoc model."""

    def test_create_product(self):
        """Test creating a product."""
        product = ProductDoc(
            ean="4006381333931",
            name="Test Product",
            brand="Test Brand",
            category="Test Category",
        )

        assert product.ean == "4006381333931"
        assert product.name == "Test Product"
        assert product.active is True

    def test_has_code(self):
        """Test checking for codes."""
        product = ProductDoc(
            ean="4006381333931",
            upc="006381333931",
            name="Test Product",
            additional_codes=["1234567890123"],
        )

        assert product.has_code("4006381333931") is True
        assert product.has_code("006381333931") is True
        assert product.has_code("1234567890123") is True
        assert product.has_code("9999999999999") is False


class TestJobDoc:
    """Tests for JobDoc model."""

    def test_create_job(self):
        """Test creating a job."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
        )

        assert job.job_id == "job-123"
        assert job.status == JobStatus.PENDING
        assert job.attempt_count == 0

    def test_can_retry(self):
        """Test retry check."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
            max_attempts=3,
        )

        assert job.can_retry() is True

        job.attempt_count = 3
        assert job.can_retry() is False

    def test_start_job(self):
        """Test starting a job."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
        )

        job.start("worker-1")

        assert job.status == JobStatus.IN_PROGRESS
        assert job.worker_id == "worker-1"
        assert job.attempt_count == 1
        assert job.started_at is not None
        assert job.locked_until is not None

    def test_complete_job(self):
        """Test completing a job."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
        )

        job.start("worker-1")
        job.complete({"codes_found": 2})

        assert job.status == JobStatus.COMPLETED
        assert job.result == {"codes_found": 2}
        assert job.locked_until is None

    def test_fail_job_with_retry(self):
        """Test failing a job with retries available."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
            max_attempts=3,
        )

        job.start("worker-1")
        job.fail("Test error")

        assert job.status == JobStatus.PENDING  # Reset for retry
        assert job.error_message == "Test error"

    def test_fail_job_no_retry(self):
        """Test failing a job with no retries left."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
            max_attempts=1,
        )

        job.start("worker-1")
        job.fail("Test error")

        assert job.status == JobStatus.FAILED

    def test_cancel_job(self):
        """Test canceling a job."""
        job = JobDoc(
            job_id="job-123",
            job_type=JobType.PREPROCESS,
            image_id="img-123",
            batch_id="batch-001",
        )

        job.cancel()

        assert job.status == JobStatus.CANCELLED
