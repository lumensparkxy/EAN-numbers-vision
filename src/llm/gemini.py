"""
Google Gemini client for AI-powered barcode extraction.

Uses the new google-genai SDK (https://github.com/googleapis/python-genai)
"""

import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from google import genai
from google.genai import types  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential  # type: ignore

from src.barcode.validator import is_valid_barcode
from src.config import get_settings
from src.models.detection import BarcodeSymbology

# Prompt for barcode extraction
BARCODE_EXTRACTION_PROMPT = """
You are a vision model specialized in reading barcodes from images.

Task:
Analyze the product image and extract any visible *linear* barcodes and their numeric codes.

Target symbologies:
- EAN-13 (13 digits, commonly used in Europe)
- EAN-8 (8 digits, for small products)
- UPC-A (12 digits, commonly used in US/Canada)
- UPC-E (6-8 digits, compressed UPC)

Processing instructions:
1. Use your vision capabilities to:
   - Locate all barcode regions in the image (even if rotated or at an angle).
   - Zoom into each barcode area to clearly see the digits printed directly under or above the bars.
2. Perform OCR on the digits that belong to the barcode itself.
   - Ignore any surrounding packaging text, prices, dates, or other numbers not attached to a barcode.
3. Validate each candidate code:
   - Make sure the length matches one of the target symbologies.
   - Apply the correct checksum rule for that symbology (EAN / UPC check digit).
   - Only keep codes where the checksum is valid and every digit is clearly readable.
4. Confidence:
   - Estimate a confidence score between 0.0 and 1.0 based on clarity of the digits and your certainty.
   - Prefer not returning a barcode at all rather than guessing unclear digits.
5. De-duplication:
   - If the same barcode appears multiple times in the image, return it only once with the highest confidence.

IMPORTANT:
- Do NOT guess or invent digits.
- If any digit is unclear, blurred, cut off, or fails checksum validation, do NOT return that code.
- Only return barcodes you can clearly read AND that pass checksum validation.

Output format:
- Return ONLY valid JSON, with no extra text, comments, or markdown.
- Use double quotes for all JSON strings.
- The top-level value MUST be a JSON array.
- Each detected barcode MUST follow this EXACT object schema:

[
  {
    "code": "1234567890123",
    "symbologyGuess": "EAN-13",
    "confidence": 0.95
  }
]

Rules:
- "symbologyGuess" MUST be one of: "EAN-13", "EAN-8", "UPC-A", "UPC-E".
- "confidence" MUST be a number between 0.0 and 1.0.

If no valid barcodes are found (or all candidates fail checksum / are unclear), return an empty array:

[]
"""


@dataclass
class GeminiResult:
    """Result from Gemini barcode extraction."""

    code: str
    symbology_guess: str
    confidence: float
    validated_symbology: BarcodeSymbology
    is_valid: bool
    checksum_valid: bool
    raw_response: dict[str, Any] | None = None


@dataclass
class GeminiResponse:
    """Full response from Gemini API."""

    results: list[GeminiResult]
    raw_text: str
    tokens_used: int | None
    error: str | None = None


class GeminiClient:
    """
    Client for Google Gemini API to extract barcodes from images.

    Uses the Gemini Vision model to analyze product images and extract
    barcode numbers when traditional decoders fail.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3-pro-preview",
        timeout: int = 120,
        max_tokens: int = 8048,
        temperature: float = 0.5,  # Gemini 3 recommends temperature=1.0
    ):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key (uses settings if not provided)
            model: Model name to use
            timeout: Request timeout in seconds
            max_tokens: Maximum tokens in response
            temperature: Model temperature (lower = more deterministic)
        """
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key_str
        if not self.api_key:
            raise ValueError("Gemini API key not configured")

        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Initialize the new genai client
        self.client = genai.Client(api_key=self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def extract_barcodes(
        self,
        image_data: bytes | BytesIO,
        custom_prompt: str | None = None,
    ) -> GeminiResponse:
        """
        Extract barcodes from an image using Gemini.

        Args:
            image_data: Image bytes or BytesIO
            custom_prompt: Optional custom prompt (uses default if not provided)

        Returns:
            GeminiResponse with extracted barcodes
        """
        # Convert to bytes if BytesIO
        if isinstance(image_data, BytesIO):
            image_data = image_data.read()

        prompt = custom_prompt or BARCODE_EXTRACTION_PROMPT

        try:
            # Create image part using the new SDK
            image_part = types.Part.from_bytes(
                data=image_data,
                mime_type="image/jpeg",
            )

            # Generate response using the new SDK
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image_part],
                config=types.GenerateContentConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                ),
            )

            # Extract text from response
            raw_text = response.text if response.text else ""

            # Parse JSON from response
            results = self._parse_response(raw_text)

            # Get token count if available
            tokens_used = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_used = getattr(response.usage_metadata, "total_token_count", None)

            return GeminiResponse(
                results=results,
                raw_text=raw_text,
                tokens_used=tokens_used,
            )

        except Exception as e:
            return GeminiResponse(
                results=[],
                raw_text="",
                tokens_used=None,
                error=str(e),
            )

    def _parse_response(self, text: str) -> list[GeminiResult]:
        """
        Parse Gemini response text to extract barcode data.

        Handles various response formats and malformed JSON.
        """
        results: list[GeminiResult] = []

        # Try to find JSON in the response
        json_data = self._extract_json(text)

        if json_data is None:
            return results

        if not isinstance(json_data, list):
            json_data = [json_data]

        for item in json_data:
            if not isinstance(item, dict):
                continue

            code = str(item.get("code", "")).strip()
            if not code:
                continue

            symbology_guess = item.get("symbologyGuess", "UNKNOWN")
            confidence = float(item.get("confidence", 0.0))

            # Validate the code
            is_valid, validated_symbology, error = is_valid_barcode(code)

            results.append(
                GeminiResult(
                    code=code,
                    symbology_guess=symbology_guess,
                    confidence=confidence,
                    validated_symbology=validated_symbology,
                    is_valid=is_valid,
                    checksum_valid=is_valid,  # Checksum is part of validation
                    raw_response=item,
                )
            )

        return results

    def _extract_json(self, text: str) -> list | dict | None:
        """
        Extract JSON from text, handling various formats.

        Tries multiple strategies:
        1. Direct JSON parse
        2. Find JSON array/object in text
        3. Extract from markdown code block
        """
        text = text.strip()

        # Strategy 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Find JSON array in text
        array_match = re.search(r"\[[\s\S]*\]", text)
        if array_match:
            try:
                return json.loads(array_match.group())
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find JSON object in text
        object_match = re.search(r"\{[\s\S]*\}", text)
        if object_match:
            try:
                return json.loads(object_match.group())
            except json.JSONDecodeError:
                pass

        # Strategy 4: Extract from markdown code block
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        return None


def create_gemini_client() -> GeminiClient:
    """Create a Gemini client with settings from environment."""
    settings = get_settings()
    return GeminiClient(
        api_key=settings.gemini_api_key_str,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout,
        max_tokens=settings.gemini_max_tokens,
        temperature=settings.gemini_temperature,
    )
