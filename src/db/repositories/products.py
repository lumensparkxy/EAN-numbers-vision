"""
Repository for product document operations.
"""

from datetime import datetime
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database

from src.models import ProductDoc


class ProductRepository:
    """Repository for product document CRUD operations."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.collection: Collection[dict[str, Any]] = db["products"]

    def create(self, product: ProductDoc) -> str:
        """Create a new product document."""
        doc = product.to_mongo()
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def upsert(self, product: ProductDoc) -> str:
        """Create or update product by EAN."""
        doc = product.to_mongo()
        doc["updated_at"] = datetime.utcnow()
        result = self.collection.update_one(
            {"ean": product.ean},
            {"$set": doc},
            upsert=True,
        )
        if result.upserted_id:
            return str(result.upserted_id)
        # Return existing document's ID
        existing = self.get_by_ean(product.ean)
        return str(existing.id) if existing and existing.id else ""

    def get_by_ean(self, ean: str) -> ProductDoc | None:
        """Get product by EAN code."""
        doc = self.collection.find_one({"ean": ean})
        if doc:
            return ProductDoc.from_mongo(doc)
        return None

    def get_by_any_code(self, code: str) -> ProductDoc | None:
        """Get product by any barcode (EAN, UPC, etc.)."""
        doc = self.collection.find_one({
            "$or": [
                {"ean": code},
                {"upc": code},
                {"ean8": code},
                {"additional_codes": code},
            ]
        })
        if doc:
            return ProductDoc.from_mongo(doc)
        return None

    def exists(self, ean: str) -> bool:
        """Check if product exists by EAN."""
        return self.collection.count_documents({"ean": ean}, limit=1) > 0

    def find_by_category(
        self,
        category: str,
        limit: int = 100,
        active_only: bool = True,
    ) -> list[ProductDoc]:
        """Find products by category."""
        query: dict[str, Any] = {"category": category}
        if active_only:
            query["active"] = True

        cursor = self.collection.find(query).limit(limit)
        return [ProductDoc.from_mongo(doc) for doc in cursor]

    def search(
        self,
        text: str,
        limit: int = 100,
    ) -> list[ProductDoc]:
        """Search products by name or brand."""
        # Simple regex search; for production, consider text indexes
        query = {
            "$or": [
                {"name": {"$regex": text, "$options": "i"}},
                {"brand": {"$regex": text, "$options": "i"}},
            ]
        }
        cursor = self.collection.find(query).limit(limit)
        return [ProductDoc.from_mongo(doc) for doc in cursor]

    def update(self, ean: str, updates: dict[str, Any]) -> bool:
        """Update product by EAN."""
        updates["updated_at"] = datetime.utcnow()
        result = self.collection.update_one(
            {"ean": ean},
            {"$set": updates},
        )
        return result.modified_count > 0

    def deactivate(self, ean: str) -> bool:
        """Deactivate a product."""
        return self.update(ean, {"active": False})

    def count(self, active_only: bool = True) -> int:
        """Count total products."""
        query: dict[str, Any] = {}
        if active_only:
            query["active"] = True
        return self.collection.count_documents(query)

    def bulk_import(self, products: list[ProductDoc]) -> dict[str, int]:
        """Bulk import products with upsert."""
        inserted = 0
        updated = 0

        for product in products:
            doc = product.to_mongo()
            doc["updated_at"] = datetime.utcnow()
            result = self.collection.update_one(
                {"ean": product.ean},
                {"$set": doc},
                upsert=True,
            )
            if result.upserted_id:
                inserted += 1
            elif result.modified_count > 0:
                updated += 1

        return {"inserted": inserted, "updated": updated}

    @staticmethod
    def create_indexes(collection: Collection[dict[str, Any]]) -> list[str]:
        """Create indexes for the products collection.
        
        Note: Using simple indexes for CosmosDB compatibility.
        Unique constraint on EAN is handled at application level.
        """
        indexes = [
            [("ean", ASCENDING)],
            [("upc", ASCENDING)],
            [("category", ASCENDING)],
            [("active", ASCENDING)],
            [("brand", ASCENDING)],
        ]
        created = []
        for index in indexes:
            name = collection.create_index(index)
            created.append(name)

        return created
