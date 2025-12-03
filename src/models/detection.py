"""
Detection document model for storing barcode detection results.
"""

from datetime import datetime
from enum import Enum

from pydantic import Field

from src.models.base import MongoBaseModel, utc_now


class DetectionSource(str, Enum):
    """Source of the barcode detection."""

    PRIMARY_ZBAR = "primary_zbar"
    PRIMARY_ZXING = "primary_zxing"
    FALLBACK_GEMINI = "fallback_gemini"
    MANUAL = "manual"


class BarcodeSymbology(str, Enum):
    """Supported barcode symbologies."""

    EAN_13 = "EAN-13"
    EAN_8 = "EAN-8"
    UPC_A = "UPC-A"
    UPC_E = "UPC-E"
    UNKNOWN = "UNKNOWN"


class DetectionDoc(MongoBaseModel):
    """
    MongoDB document for a barcode detection result.

    Collection: detections
    """

    # References
    image_id: str = Field(..., description="Reference to parent image")
    batch_id: str = Field(..., description="Batch for easier querying")
    source_filename: str | None = Field(None, description="Original filename for easier tracing")

    # Barcode data
    code: str = Field(..., description="The detected barcode value")
    symbology: BarcodeSymbology = Field(default=BarcodeSymbology.UNKNOWN)
    normalized_code: str | None = Field(None, description="Normalized code (e.g., UPC-A to EAN-13)")

    # Detection metadata
    source: DetectionSource = Field(..., description="How the code was detected")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Detection confidence")
    rotation_degrees: int | None = Field(None, description="Image rotation when detected")

    # Validation
    checksum_valid: bool = Field(False, description="Whether checksum validation passed")
    length_valid: bool = Field(False, description="Whether length is valid for symbology")
    numeric_only: bool = Field(False, description="Whether code contains only digits")

    # Ambiguity handling
    ambiguous: bool = Field(
        False, description="True if multiple codes detected and manual review needed"
    )
    chosen: bool = Field(False, description="True if selected during manual review")
    rejected: bool = Field(False, description="True if rejected during manual review")

    # Product lookup
    product_found: bool = Field(False, description="Whether product exists in catalog")
    product_id: str | None = Field(None, description="Reference to product if found")

    # Gemini-specific (for fallback)
    gemini_confidence: float | None = Field(None, description="Gemini's reported confidence")
    gemini_symbology_guess: str | None = Field(None, description="Gemini's guess at symbology")

    # Timestamps
    detected_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None

    def mark_as_valid(self) -> bool:
        """Check if this detection is considered valid."""
        return self.checksum_valid and self.length_valid and self.numeric_only

    def mark_chosen(self, reviewer: str | None = None) -> None:
        """Mark this detection as the chosen one during manual review."""
        self.chosen = True
        self.ambiguous = False
        self.reviewed_at = utc_now()
        self.reviewed_by = reviewer

    def mark_rejected(self, reviewer: str | None = None) -> None:
        """Mark this detection as rejected during manual review."""
        self.rejected = True
        self.reviewed_at = utc_now()
        self.reviewed_by = reviewer


def normalize_to_ean13(code: str, symbology: BarcodeSymbology) -> str | None:
    """
    Normalize barcode to EAN-13 format.

    - UPC-A (12 digits): Prefix with '0' to get EAN-13
    - EAN-8: Cannot be normalized to EAN-13 (different product)
    - UPC-E: Would need expansion (complex, skip for now)
    """
    if symbology == BarcodeSymbology.UPC_A and len(code) == 12:
        return "0" + code
    elif symbology == BarcodeSymbology.EAN_13 and len(code) == 13:
        return code
    return None
