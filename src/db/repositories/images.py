"""
Repository for image document operations.
"""

from datetime import datetime
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database

from src.models import ImageDoc, ImageStatus


class ImageRepository:
    """Repository for image document CRUD operations."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.collection: Collection[dict[str, Any]] = db["images"]

    def create(self, image: ImageDoc) -> str:
        """Create a new image document."""
        doc = image.to_mongo()
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get_by_id(self, image_id: str) -> ImageDoc | None:
        """Get image by image_id."""
        doc = self.collection.find_one({"image_id": image_id})
        if doc:
            return ImageDoc.from_mongo(doc)
        return None

    def get_by_source_filename(self, batch_id: str, source_filename: str) -> ImageDoc | None:
        """Get image by batch_id and source_filename (for duplicate detection)."""
        doc = self.collection.find_one(
            {
                "batch_id": batch_id,
                "source_filename": source_filename,
            }
        )
        if doc:
            return ImageDoc.from_mongo(doc)
        return None

    def get_by_object_id(self, object_id: str) -> ImageDoc | None:
        """Get image by MongoDB _id."""
        from bson import ObjectId

        doc = self.collection.find_one({"_id": ObjectId(object_id)})
        if doc:
            return ImageDoc.from_mongo(doc)
        return None

    def update_status(
        self,
        image_id: str,
        status: ImageStatus,
        additional_updates: dict[str, Any] | None = None,
    ) -> bool:
        """Update image status."""
        update = {
            "$set": {
                "status": status.value,
                "status_updated_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        }
        if additional_updates:
            update["$set"].update(additional_updates)

        result = self.collection.update_one({"image_id": image_id}, update)
        return result.modified_count > 0

    def update(self, image_id: str, updates: dict[str, Any]) -> bool:
        """Update image with arbitrary fields."""
        updates["updated_at"] = datetime.utcnow()
        result = self.collection.update_one({"image_id": image_id}, {"$set": updates})
        return result.modified_count > 0

    def find_by_status(
        self,
        status: ImageStatus,
        limit: int = 100,
        batch_id: str | None = None,
    ) -> list[ImageDoc]:
        """Find images by status."""
        query: dict[str, Any] = {"status": status.value}
        if batch_id:
            query["batch_id"] = batch_id

        cursor = self.collection.find(query).limit(limit).sort("created_at", ASCENDING)
        return [ImageDoc.from_mongo(doc) for doc in cursor]

    def find_pending(self, limit: int = 100) -> list[ImageDoc]:
        """Find pending images ready for preprocessing."""
        return self.find_by_status(ImageStatus.PENDING, limit)

    def find_preprocessed(self, limit: int = 100) -> list[ImageDoc]:
        """Find preprocessed images ready for primary decoding.

        Excludes images already marked for fallback (already tried by primary).
        """
        query = {
            "status": ImageStatus.PREPROCESSED.value,
            "$or": [
                {"processing.needs_fallback": {"$exists": False}},
                {"processing.needs_fallback": False},
            ],
        }
        cursor = self.collection.find(query).limit(limit).sort("created_at", ASCENDING)
        return [ImageDoc.from_mongo(doc) for doc in cursor]

    def find_needing_fallback(self, limit: int = 100) -> list[ImageDoc]:
        """Find images that need fallback decoding."""
        query = {
            "status": {"$in": [ImageStatus.PREPROCESSED.value, ImageStatus.DECODED_PRIMARY.value]},
            "processing.needs_fallback": True,
        }
        cursor = self.collection.find(query).limit(limit).sort("created_at", ASCENDING)
        return [ImageDoc.from_mongo(doc) for doc in cursor]

    def find_for_manual_review(self, limit: int = 100) -> list[ImageDoc]:
        """Find images pending manual review."""
        return self.find_by_status(ImageStatus.MANUAL_REVIEW, limit)

    def find_failed_for_retry(
        self,
        limit: int = 100,
        max_attempts: int = 3,
    ) -> list[ImageDoc]:
        """
        Find failed images eligible for retry.

        Only returns images that:
        - Have status FAILED
        - Have fewer than max_attempts Gemini attempts (fallback_attempts)

        Args:
            limit: Maximum number of images to return
            max_attempts: Maximum total Gemini attempts allowed

        Returns:
            List of ImageDoc eligible for retry
        """
        # Query for failed images with fewer than max_attempts
        # We check the size of processing.fallback_attempts array
        query = {
            "status": ImageStatus.FAILED.value,
            "$expr": {
                "$lt": [
                    {"$size": {"$ifNull": ["$processing.fallback_attempts", []]}},
                    max_attempts,
                ]
            },
        }
        cursor = self.collection.find(query).limit(limit).sort("created_at", ASCENDING)
        return [ImageDoc.from_mongo(doc) for doc in cursor]

    def get_stats(self, batch_id: str | None = None) -> dict[str, int]:
        """Get count of images by status."""
        match_stage: dict[str, Any] = {}
        if batch_id:
            match_stage["batch_id"] = batch_id

        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]

        result = list(self.collection.aggregate(pipeline))
        return {item["_id"]: item["count"] for item in result}

    def add_processing_error(
        self,
        image_id: str,
        stage: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Add a processing error to the image."""
        error = {
            "stage": stage,
            "message": message,
            "timestamp": datetime.utcnow(),
            "details": details,
        }
        result = self.collection.update_one(
            {"image_id": image_id},
            {
                "$push": {"processing.errors": error},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return result.modified_count > 0

    def increment_detection_count(self, image_id: str, count: int = 1) -> bool:
        """Increment the detection count for an image."""
        result = self.collection.update_one(
            {"image_id": image_id},
            {
                "$inc": {"detection_count": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return result.modified_count > 0

    def count_by_batch(self, batch_id: str) -> int:
        """Count images in a batch."""
        return self.collection.count_documents({"batch_id": batch_id})

    @staticmethod
    def create_indexes(collection: Collection[dict[str, Any]]) -> list[str]:
        """Create indexes for the images collection.

        Note: Using simple indexes for CosmosDB compatibility.
        CosmosDB doesn't support compound indexes with nested paths.
        """
        indexes = [
            [("status", ASCENDING)],
            [("batch_id", ASCENDING)],
            [("image_id", ASCENDING)],
            [("created_at", ASCENDING)],
            [("source_filename", ASCENDING)],  # For duplicate detection
        ]
        created = []
        for index in indexes:
            name = collection.create_index(index)
            created.append(name)
        return created
