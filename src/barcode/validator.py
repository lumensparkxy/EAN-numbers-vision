"""
Barcode validation utilities for EAN/UPC codes.
"""

from src.models.detection import BarcodeSymbology


def calculate_ean13_checksum(code: str) -> int:
    """
    Calculate EAN-13 checksum digit.

    Algorithm:
    1. Multiply digits at odd positions (1, 3, 5, ...) by 1
    2. Multiply digits at even positions (2, 4, 6, ...) by 3
    3. Sum all results
    4. Checksum = (10 - (sum mod 10)) mod 10
    """
    if len(code) < 12:
        raise ValueError("Code must have at least 12 digits for EAN-13")

    total = 0
    for i, digit in enumerate(code[:12]):
        if not digit.isdigit():
            raise ValueError(f"Invalid character in code: {digit}")
        weight = 1 if i % 2 == 0 else 3
        total += int(digit) * weight

    return (10 - (total % 10)) % 10


def validate_ean13_checksum(code: str) -> bool:
    """
    Validate EAN-13 checksum.

    Args:
        code: 13-digit EAN code

    Returns:
        True if checksum is valid
    """
    if len(code) != 13:
        return False
    if not code.isdigit():
        return False

    expected_checksum = calculate_ean13_checksum(code)
    actual_checksum = int(code[-1])

    return expected_checksum == actual_checksum


def calculate_ean8_checksum(code: str) -> int:
    """
    Calculate EAN-8 checksum digit.

    Algorithm is similar to EAN-13 but with 7 digits.
    """
    if len(code) < 7:
        raise ValueError("Code must have at least 7 digits for EAN-8")

    total = 0
    for i, digit in enumerate(code[:7]):
        if not digit.isdigit():
            raise ValueError(f"Invalid character in code: {digit}")
        # For EAN-8, odd positions (1, 3, 5, 7) have weight 3
        weight = 3 if i % 2 == 0 else 1
        total += int(digit) * weight

    return (10 - (total % 10)) % 10


def validate_ean8_checksum(code: str) -> bool:
    """
    Validate EAN-8 checksum.

    Args:
        code: 8-digit EAN code

    Returns:
        True if checksum is valid
    """
    if len(code) != 8:
        return False
    if not code.isdigit():
        return False

    expected_checksum = calculate_ean8_checksum(code)
    actual_checksum = int(code[-1])

    return expected_checksum == actual_checksum


def validate_upc_checksum(code: str) -> bool:
    """
    Validate UPC-A checksum.

    UPC-A uses the same algorithm as EAN-13 (UPC-A is essentially EAN-13 with leading 0).

    Args:
        code: 12-digit UPC-A code

    Returns:
        True if checksum is valid
    """
    if len(code) != 12:
        return False
    if not code.isdigit():
        return False

    # Calculate checksum using EAN-13 algorithm on first 11 digits
    # but with weights reversed (odd=3, even=1 for positions 1-11)
    total = 0
    for i, digit in enumerate(code[:11]):
        weight = 3 if i % 2 == 0 else 1
        total += int(digit) * weight

    expected_checksum = (10 - (total % 10)) % 10
    actual_checksum = int(code[-1])

    return expected_checksum == actual_checksum


def detect_symbology(code: str) -> BarcodeSymbology:
    """
    Detect barcode symbology from code.

    Args:
        code: Barcode string

    Returns:
        Detected symbology
    """
    if not code.isdigit():
        return BarcodeSymbology.UNKNOWN

    length = len(code)

    if length == 13:
        return BarcodeSymbology.EAN_13
    elif length == 8:
        return BarcodeSymbology.EAN_8
    elif length == 12:
        return BarcodeSymbology.UPC_A
    elif length == 6 or length == 7:
        return BarcodeSymbology.UPC_E
    else:
        return BarcodeSymbology.UNKNOWN


def is_valid_barcode(code: str) -> tuple[bool, BarcodeSymbology, str]:
    """
    Validate a barcode completely.

    Args:
        code: Barcode string

    Returns:
        Tuple of (is_valid, symbology, error_message)
    """
    # Check numeric
    if not code.isdigit():
        return False, BarcodeSymbology.UNKNOWN, "Code contains non-numeric characters"

    symbology = detect_symbology(code)

    if symbology == BarcodeSymbology.UNKNOWN:
        return False, symbology, f"Unsupported code length: {len(code)}"

    # Validate checksum based on symbology
    if symbology == BarcodeSymbology.EAN_13:
        if validate_ean13_checksum(code):
            return True, symbology, ""
        else:
            return False, symbology, "Invalid EAN-13 checksum"

    elif symbology == BarcodeSymbology.EAN_8:
        if validate_ean8_checksum(code):
            return True, symbology, ""
        else:
            return False, symbology, "Invalid EAN-8 checksum"

    elif symbology == BarcodeSymbology.UPC_A:
        if validate_upc_checksum(code):
            return True, symbology, ""
        else:
            return False, symbology, "Invalid UPC-A checksum"

    elif symbology == BarcodeSymbology.UPC_E:
        # UPC-E validation is more complex; accept for now
        return True, symbology, ""

    return False, symbology, "Unknown validation error"


def normalize_barcode(code: str, symbology: BarcodeSymbology) -> str:
    """
    Normalize barcode to standard format.

    - UPC-A: Convert to EAN-13 by adding leading 0
    - Others: Return as-is

    Args:
        code: Barcode string
        symbology: Detected symbology

    Returns:
        Normalized barcode
    """
    if symbology == BarcodeSymbology.UPC_A and len(code) == 12:
        return "0" + code
    return code
