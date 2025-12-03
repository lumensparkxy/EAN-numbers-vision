"""
Repository for job document operations (queue system).
"""

from datetime import datetime, timedelta
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.database import Database

from src.models import JobDoc, JobStatus, JobType


class JobRepository:
    """Repository for job queue operations."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.collection: Collection[dict[str, Any]] = db["jobs"]

    def create(self, job: JobDoc) -> str:
        """Create a new job."""
        doc = job.to_mongo()
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def enqueue(
        self,
        job_type: JobType,
        image_id: str,
        batch_id: str,
        priority: int = 0,
        scheduled_for: datetime | None = None,
    ) -> str:
        """Enqueue a new job."""
        import uuid

        job = JobDoc(
            job_id=str(uuid.uuid4()),
            job_type=job_type,
            image_id=image_id,
            batch_id=batch_id,
            priority=priority,
            scheduled_for=scheduled_for or datetime.utcnow(),
        )
        return self.create(job)

    def get_by_id(self, job_id: str) -> JobDoc | None:
        """Get job by job_id."""
        doc = self.collection.find_one({"job_id": job_id})
        if doc:
            return JobDoc.from_mongo(doc)
        return None

    def dequeue(
        self,
        job_type: JobType | None = None,
        worker_id: str = "default",
        lock_duration_seconds: int = 300,
    ) -> JobDoc | None:
        """
        Atomically dequeue and lock a pending job.

        Uses findAndModify for atomic operations.
        """
        now = datetime.utcnow()
        lock_until = now + timedelta(seconds=lock_duration_seconds)

        query: dict[str, Any] = {
            "status": JobStatus.PENDING.value,
            "scheduled_for": {"$lte": now},
        }
        if job_type:
            query["job_type"] = job_type.value

        # Find expired locks too (for jobs that crashed)
        query_with_expired = {
            "$or": [
                query,
                {
                    "status": JobStatus.IN_PROGRESS.value,
                    "locked_until": {"$lt": now},
                },
            ]
        }

        update = {
            "$set": {
                "status": JobStatus.IN_PROGRESS.value,
                "worker_id": worker_id,
                "started_at": now,
                "locked_until": lock_until,
                "updated_at": now,
            },
            "$inc": {"attempt_count": 1},
        }

        doc = self.collection.find_one_and_update(
            query_with_expired,
            update,
            sort=[("priority", -1), ("scheduled_for", 1)],
            return_document=True,
        )

        if doc:
            return JobDoc.from_mongo(doc)
        return None

    def complete(
        self,
        job_id: str,
        result: dict[str, Any] | None = None,
    ) -> bool:
        """Mark job as completed."""
        now = datetime.utcnow()
        update_result = self.collection.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": JobStatus.COMPLETED.value,
                    "completed_at": now,
                    "result": result,
                    "locked_until": None,
                    "updated_at": now,
                }
            },
        )
        return update_result.modified_count > 0

    def fail(
        self,
        job_id: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> bool:
        """
        Mark job as failed.

        If retries remain, resets to pending. Otherwise marks as failed.
        """
        job = self.get_by_id(job_id)
        if not job:
            return False

        now = datetime.utcnow()

        if job.attempt_count < max_attempts:
            # Retry: reset to pending with backoff
            backoff_seconds = 60 * (2 ** job.attempt_count)  # Exponential backoff
            scheduled_for = now + timedelta(seconds=backoff_seconds)

            update = {
                "$set": {
                    "status": JobStatus.PENDING.value,
                    "worker_id": None,
                    "error_message": error_message,
                    "error_details": error_details,
                    "locked_until": None,
                    "scheduled_for": scheduled_for,
                    "updated_at": now,
                }
            }
        else:
            # No more retries
            update = {
                "$set": {
                    "status": JobStatus.FAILED.value,
                    "completed_at": now,
                    "error_message": error_message,
                    "error_details": error_details,
                    "locked_until": None,
                    "updated_at": now,
                }
            }

        result = self.collection.update_one({"job_id": job_id}, update)
        return result.modified_count > 0

    def cancel(self, job_id: str) -> bool:
        """Cancel a job."""
        now = datetime.utcnow()
        result = self.collection.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": JobStatus.CANCELLED.value,
                    "completed_at": now,
                    "locked_until": None,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count > 0

    def find_by_status(
        self,
        status: JobStatus,
        job_type: JobType | None = None,
        limit: int = 100,
    ) -> list[JobDoc]:
        """Find jobs by status."""
        query: dict[str, Any] = {"status": status.value}
        if job_type:
            query["job_type"] = job_type.value

        cursor = self.collection.find(query).limit(limit)
        return [JobDoc.from_mongo(doc) for doc in cursor]

    def count_pending(self, job_type: JobType | None = None) -> int:
        """Count pending jobs."""
        query: dict[str, Any] = {"status": JobStatus.PENDING.value}
        if job_type:
            query["job_type"] = job_type.value
        return self.collection.count_documents(query)

    def get_stats(self) -> dict[str, Any]:
        """Get job queue statistics."""
        pipeline = [
            {
                "$group": {
                    "_id": {"type": "$job_type", "status": "$status"},
                    "count": {"$sum": 1},
                }
            }
        ]

        result = list(self.collection.aggregate(pipeline))
        stats: dict[str, dict[str, int]] = {}

        for item in result:
            job_type = item["_id"]["type"]
            status = item["_id"]["status"]
            if job_type not in stats:
                stats[job_type] = {}
            stats[job_type][status] = item["count"]

        return stats

    def cleanup_old_completed(self, days: int = 7) -> int:
        """Delete completed/failed jobs older than N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = self.collection.delete_many({
            "status": {"$in": [JobStatus.COMPLETED.value, JobStatus.FAILED.value]},
            "completed_at": {"$lt": cutoff},
        })
        return result.deleted_count

    def exists_for_image(self, image_id: str, job_type: JobType) -> bool:
        """Check if a job already exists for an image."""
        return self.collection.count_documents({
            "image_id": image_id,
            "job_type": job_type.value,
            "status": {"$in": [JobStatus.PENDING.value, JobStatus.IN_PROGRESS.value]},
        }, limit=1) > 0

    @staticmethod
    def create_indexes(collection: Collection[dict[str, Any]]) -> list[str]:
        """Create indexes for the jobs collection.
        
        Note: Using simple indexes for CosmosDB compatibility.
        """
        indexes = [
            [("status", ASCENDING)],
            [("job_type", ASCENDING)],
            [("job_id", ASCENDING)],
            [("image_id", ASCENDING)],
            [("scheduled_for", ASCENDING)],
            [("locked_until", ASCENDING)],
        ]
        created = []
        for index in indexes:
            name = collection.create_index(index)
            created.append(name)
        return created
