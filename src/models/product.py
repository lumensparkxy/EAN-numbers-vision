"""
Product document model for the product catalog.
"""

from datetime import datetime

from pydantic import Field

from src.models.base import MongoBaseModel, utc_now


class ProductDoc(MongoBaseModel):
    """
    MongoDB document for a product in the catalog.

    Collection: products
    """

    # Primary identifier
    ean: str = Field(..., description="Primary EAN-13 barcode")

    # Alternative codes
    upc: str | None = Field(None, description="UPC-A code if different")
    ean8: str | None = Field(None, description="EAN-8 if product has one")
    additional_codes: list[str] = Field(
        default_factory=list, description="Other barcodes for this product"
    )

    # Product info
    name: str = Field(..., description="Product name")
    brand: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None

    # Attributes
    size: str | None = Field(None, description="Size/weight (e.g., '500g', '1L')")
    unit: str | None = Field(None, description="Unit type")
    pack_size: int | None = Field(None, description="Number of items in pack")

    # External references
    external_id: str | None = Field(None, description="ID in external system")
    sku: str | None = Field(None, description="Internal SKU")

    # Status
    active: bool = Field(True, description="Whether product is currently active")

    # Metadata
    image_url: str | None = None
    source: str | None = Field(None, description="Data source (e.g., 'catalog_import', 'manual')")

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def has_code(self, code: str) -> bool:
        """Check if product has a specific barcode."""
        codes = [self.ean]
        if self.upc:
            codes.append(self.upc)
        if self.ean8:
            codes.append(self.ean8)
        codes.extend(self.additional_codes)
        return code in codes
