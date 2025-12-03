"""
Barcode decoder using pyzbar (ZBar) library.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image
from pyzbar import pyzbar
from pyzbar.pyzbar import Decoded, ZBarSymbol

from src.barcode.validator import (
    detect_symbology,
    is_valid_barcode,
    normalize_barcode,
)
from src.models.detection import BarcodeSymbology


@dataclass
class BarcodeResult:
    """Result of a barcode detection."""

    code: str
    symbology: BarcodeSymbology
    normalized_code: str
    is_valid: bool
    checksum_valid: bool
    length_valid: bool
    numeric_only: bool
    rotation: int
    confidence: float | None = None
    rect: tuple[int, int, int, int] | None = None  # x, y, width, height
    polygon: list[tuple[int, int]] | None = None
    error: str | None = None


class BarcodeDecoder:
    """
    Barcode decoder using ZBar via pyzbar.

    Supports:
    - EAN-13
    - EAN-8
    - UPC-A
    - UPC-E
    """

    # Map pyzbar symbol types to our symbology
    SYMBOL_MAP = {
        "EAN13": BarcodeSymbology.EAN_13,
        "EAN8": BarcodeSymbology.EAN_8,
        "UPCA": BarcodeSymbology.UPC_A,
        "UPCE": BarcodeSymbology.UPC_E,
    }

    # Symbol types to scan for
    SCAN_SYMBOLS = [
        ZBarSymbol.EAN13,
        ZBarSymbol.EAN8,
        ZBarSymbol.UPCA,
        ZBarSymbol.UPCE,
    ]

    def __init__(
        self,
        try_rotations: bool = True,
        rotation_angles: list[int] | None = None,
    ):
        """
        Initialize decoder.

        Args:
            try_rotations: Whether to try multiple rotations
            rotation_angles: Specific angles to try (default: [0, 180])
        """
        self.try_rotations = try_rotations
        self.rotation_angles = rotation_angles or [0, 180]

    def decode(
        self,
        image_data: bytes | BytesIO | np.ndarray | Image.Image,
    ) -> list[BarcodeResult]:
        """
        Decode barcodes from an image.

        Args:
            image_data: Image as bytes, BytesIO, numpy array, or PIL Image

        Returns:
            List of detected barcodes
        """
        # Convert input to PIL Image
        pil_image = self._to_pil_image(image_data)

        # Convert to grayscale for better detection
        if pil_image.mode != "L":
            pil_image = pil_image.convert("L")

        all_results: list[BarcodeResult] = []
        seen_codes: set[str] = set()

        if self.try_rotations:
            for angle in self.rotation_angles:
                rotated = self._rotate_image(pil_image, angle) if angle != 0 else pil_image
                results = self._decode_image(rotated, angle)

                for result in results:
                    if result.code not in seen_codes:
                        seen_codes.add(result.code)
                        all_results.append(result)
        else:
            all_results = self._decode_image(pil_image, 0)

        return all_results

    def decode_file(self, file_path: str) -> list[BarcodeResult]:
        """Decode barcodes from an image file."""
        with open(file_path, "rb") as f:
            return self.decode(f.read())

    def _to_pil_image(
        self,
        image_data: bytes | BytesIO | np.ndarray | Image.Image,
    ) -> Image.Image:
        """Convert various image formats to PIL Image."""
        if isinstance(image_data, Image.Image):
            return image_data
        elif isinstance(image_data, np.ndarray):
            return Image.fromarray(image_data)
        elif isinstance(image_data, bytes):
            return Image.open(BytesIO(image_data))
        elif isinstance(image_data, BytesIO):
            return Image.open(image_data)
        else:
            raise TypeError(f"Unsupported image type: {type(image_data)}")

    def _rotate_image(self, image: Image.Image, angle: int) -> Image.Image:
        """Rotate image by specified angle."""
        if angle == 0:
            return image
        return image.rotate(angle, expand=True)

    def _decode_image(
        self,
        image: Image.Image,
        rotation: int,
    ) -> list[BarcodeResult]:
        """Decode barcodes from a single image orientation."""
        results: list[BarcodeResult] = []

        try:
            # Use pyzbar to decode
            decoded_objects: Sequence[Decoded] = pyzbar.decode(
                image,
                symbols=self.SCAN_SYMBOLS,
            )

            for obj in decoded_objects:
                result = self._process_decoded(obj, rotation)
                if result:
                    results.append(result)

        except Exception as e:
            # Return error result
            results.append(
                BarcodeResult(
                    code="",
                    symbology=BarcodeSymbology.UNKNOWN,
                    normalized_code="",
                    is_valid=False,
                    checksum_valid=False,
                    length_valid=False,
                    numeric_only=False,
                    rotation=rotation,
                    error=str(e),
                )
            )

        return results

    def _process_decoded(
        self,
        decoded: Decoded,
        rotation: int,
    ) -> BarcodeResult | None:
        """Process a decoded barcode object."""
        try:
            # Get code as string
            code = decoded.data.decode("utf-8")

            # Get symbology
            symbol_type = decoded.type
            symbology = self.SYMBOL_MAP.get(symbol_type, BarcodeSymbology.UNKNOWN)

            # If symbology unknown, try to detect from code
            if symbology == BarcodeSymbology.UNKNOWN:
                symbology = detect_symbology(code)

            # Validate
            is_valid, detected_symbology, error = is_valid_barcode(code)

            # Use detected symbology if original was unknown
            if symbology == BarcodeSymbology.UNKNOWN:
                symbology = detected_symbology

            # Normalize
            normalized = normalize_barcode(code, symbology)

            # Extract location
            rect = decoded.rect
            polygon = [(p.x, p.y) for p in decoded.polygon] if decoded.polygon else None

            return BarcodeResult(
                code=code,
                symbology=symbology,
                normalized_code=normalized,
                is_valid=is_valid,
                checksum_valid=is_valid,  # Simplified: checksum check is part of validation
                length_valid=len(code) in [8, 12, 13],
                numeric_only=code.isdigit(),
                rotation=rotation,
                rect=(rect.left, rect.top, rect.width, rect.height) if rect else None,
                polygon=polygon,
                error=error if not is_valid else None,
            )

        except Exception as e:
            return BarcodeResult(
                code="",
                symbology=BarcodeSymbology.UNKNOWN,
                normalized_code="",
                is_valid=False,
                checksum_valid=False,
                length_valid=False,
                numeric_only=False,
                rotation=rotation,
                error=str(e),
            )


def decode_image(
    image_data: bytes | BytesIO | np.ndarray,
    try_rotations: bool = True,
) -> list[BarcodeResult]:
    """
    Convenience function to decode barcodes from an image.

    Args:
        image_data: Image data
        try_rotations: Whether to try rotated versions

    Returns:
        List of barcode results
    """
    decoder = BarcodeDecoder(try_rotations=try_rotations)
    return decoder.decode(image_data)
