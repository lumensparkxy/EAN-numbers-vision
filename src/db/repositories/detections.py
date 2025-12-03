"""
Repository for detection document operations.
"""

from datetime import datetime
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database

from src.models import DetectionDoc, DetectionSource


class DetectionRepository:
    """Repository for detection document CRUD operations."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.collection: Collection[dict[str, Any]] = db["detections"]

    def create(self, detection: DetectionDoc) -> str:
        """Create a new detection document."""
        doc = detection.to_mongo()
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def create_many(self, detections: list[DetectionDoc]) -> list[str]:
        """Create multiple detection documents."""
        if not detections:
            return []
        docs = [d.to_mongo() for d in detections]
        result = self.collection.insert_many(docs)
        return [str(oid) for oid in result.inserted_ids]

    def get_by_id(self, object_id: str) -> DetectionDoc | None:
        """Get detection by MongoDB _id."""
        from bson import ObjectId

        doc = self.collection.find_one({"_id": ObjectId(object_id)})
        if doc:
            return DetectionDoc.from_mongo(doc)
        return None

    def find_by_image(self, image_id: str) -> list[DetectionDoc]:
        """Find all detections for an image."""
        cursor = self.collection.find({"image_id": image_id})
        return [DetectionDoc.from_mongo(doc) for doc in cursor]

    def exists_for_image(self, image_id: str) -> bool:
        """Check if any detections exist for an image (for idempotency)."""
        return self.collection.count_documents({"image_id": image_id}, limit=1) > 0

    def find_by_code(self, code: str) -> list[DetectionDoc]:
        """Find all detections with a specific code."""
        cursor = self.collection.find({"code": code})
        return [DetectionDoc.from_mongo(doc) for doc in cursor]

    def find_by_source_filename(self, source_filename: str) -> list[DetectionDoc]:
        """Find all detections for a specific source filename."""
        cursor = self.collection.find({"source_filename": source_filename})
        return [DetectionDoc.from_mongo(doc) for doc in cursor]

    def find_valid_by_image(self, image_id: str) -> list[DetectionDoc]:
        """Find valid detections for an image."""
        cursor = self.collection.find({
            "image_id": image_id,
            "checksum_valid": True,
            "length_valid": True,
            "numeric_only": True,
            "rejected": False,
        })
        return [DetectionDoc.from_mongo(doc) for doc in cursor]

    def find_ambiguous(self, limit: int = 100) -> list[DetectionDoc]:
        """Find ambiguous detections needing review."""
        cursor = self.collection.find({"ambiguous": True}).limit(limit)
        return [DetectionDoc.from_mongo(doc) for doc in cursor]

    def mark_chosen(
        self,
        detection_id: str,
        reviewer: str | None = None,
    ) -> bool:
        """Mark a detection as chosen during manual review."""
        from bson import ObjectId

        result = self.collection.update_one(
            {"_id": ObjectId(detection_id)},
            {
                "$set": {
                    "chosen": True,
                    "ambiguous": False,
                    "reviewed_at": datetime.utcnow(),
                    "reviewed_by": reviewer,
                }
            },
        )
        return result.modified_count > 0

    def mark_rejected(
        self,
        detection_id: str,
        reviewer: str | None = None,
    ) -> bool:
        """Mark a detection as rejected during manual review."""
        from bson import ObjectId

        result = self.collection.update_one(
            {"_id": ObjectId(detection_id)},
            {
                "$set": {
                    "rejected": True,
                    "reviewed_at": datetime.utcnow(),
                    "reviewed_by": reviewer,
                }
            },
        )
        return result.modified_count > 0

    def reject_other_detections(
        self,
        image_id: str,
        chosen_detection_id: str,
        reviewer: str | None = None,
    ) -> int:
        """Reject all other detections for an image."""
        from bson import ObjectId

        result = self.collection.update_many(
            {
                "image_id": image_id,
                "_id": {"$ne": ObjectId(chosen_detection_id)},
            },
            {
                "$set": {
                    "rejected": True,
                    "ambiguous": False,
                    "reviewed_at": datetime.utcnow(),
                    "reviewed_by": reviewer,
                }
            },
        )
        return result.modified_count

    def get_stats_by_source(self, batch_id: str | None = None) -> dict[str, int]:
        """Get detection count by source."""
        match_stage: dict[str, Any] = {}
        if batch_id:
            match_stage["batch_id"] = batch_id

        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        ]

        result = list(self.collection.aggregate(pipeline))
        return {item["_id"]: item["count"] for item in result}

    def count_by_validation(self, batch_id: str | None = None) -> dict[str, int]:
        """Get counts by validation status."""
        match_stage: dict[str, Any] = {}
        if batch_id:
            match_stage["batch_id"] = batch_id

        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "checksum_valid": {
                        "$sum": {"$cond": ["$checksum_valid", 1, 0]}
                    },
                    "product_found": {
                        "$sum": {"$cond": ["$product_found", 1, 0]}
                    },
                    "ambiguous": {"$sum": {"$cond": ["$ambiguous", 1, 0]}},
                }
            },
        ]

        result = list(self.collection.aggregate(pipeline))
        if result:
            return result[0]
        return {"total": 0, "checksum_valid": 0, "product_found": 0, "ambiguous": 0}

    @staticmethod
    def create_indexes(collection: Collection[dict[str, Any]]) -> list[str]:
        """Create indexes for the detections collection.
        
        Note: Using simple indexes for CosmosDB compatibility.
        """
        indexes = [
            [("image_id", ASCENDING)],
            [("code", ASCENDING)],
            [("batch_id", ASCENDING)],
            [("source", ASCENDING)],
            [("ambiguous", ASCENDING)],
            [("checksum_valid", ASCENDING)],
            [("source_filename", ASCENDING)],
        ]
        created = []
        for index in indexes:
            name = collection.create_index(index)
            created.append(name)
        return created
