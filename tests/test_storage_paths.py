"""
Tests for blob storage path utilities.
"""

import pytest

from src.storage.paths import BlobPaths


class TestBlobPaths:
    """Tests for blob path generation."""

    def test_incoming_path(self):
        """Test incoming path generation."""
        path = BlobPaths.incoming("batch_001", "img_123")
        assert path == "incoming/batch_001/img_123.jpg"

    def test_incoming_path_custom_extension(self):
        """Test incoming path with custom extension."""
        path = BlobPaths.incoming("batch_001", "img_123", "png")
        assert path == "incoming/batch_001/img_123.png"

    def test_preprocessed_path(self):
        """Test preprocessed path generation."""
        path = BlobPaths.preprocessed("batch_001", "img_123")
        assert path == "preprocessed/batch_001/img_123_norm.jpg"

    def test_processed_path(self):
        """Test processed path generation."""
        path = BlobPaths.processed("batch_001", "img_123")
        assert path == "processed/batch_001/img_123.jpg"

    def test_failed_path(self):
        """Test failed path generation."""
        path = BlobPaths.failed("batch_001", "img_123")
        assert path == "failed/batch_001/img_123.jpg"

    def test_manual_review_path(self):
        """Test manual review path generation."""
        path = BlobPaths.manual_review("batch_001", "img_123")
        assert path == "manual-review/batch_001/img_123.jpg"


class TestPathExtraction:
    """Tests for extracting info from blob paths."""

    def test_extract_batch_and_image_id(self):
        """Test extraction of batch and image IDs."""
        batch_id, image_id = BlobPaths.extract_batch_and_image_id("incoming/batch_001/img_123.jpg")
        assert batch_id == "batch_001"
        assert image_id == "img_123"

    def test_extract_from_preprocessed(self):
        """Test extraction from preprocessed path."""
        batch_id, image_id = BlobPaths.extract_batch_and_image_id(
            "preprocessed/batch_001/img_123_norm.jpg"
        )
        assert batch_id == "batch_001"
        assert image_id == "img_123"  # _norm suffix should be removed

    def test_get_folder(self):
        """Test folder extraction."""
        assert BlobPaths.get_folder("incoming/batch/img.jpg") == "incoming"
        assert BlobPaths.get_folder("processed/batch/img.jpg") == "processed"

    def test_get_extension(self):
        """Test extension extraction."""
        assert BlobPaths.get_extension("path/to/file.jpg") == "jpg"
        assert BlobPaths.get_extension("path/to/file.png") == "png"
        assert BlobPaths.get_extension("noextension") == ""

    def test_change_folder(self):
        """Test folder change."""
        new_path = BlobPaths.change_folder("incoming/batch_001/img.jpg", "processed")
        assert new_path == "processed/batch_001/img.jpg"

    def test_invalid_path_format(self):
        """Test handling of invalid paths."""
        with pytest.raises(ValueError):
            BlobPaths.extract_batch_and_image_id("invalid")

        with pytest.raises(ValueError):
            BlobPaths.change_folder("invalid", "processed")
