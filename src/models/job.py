"""
Job document model for the job queue system.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.models.base import MongoBaseModel, utc_now


class JobType(str, Enum):
    """Types of processing jobs."""

    PREPROCESS = "preprocess"
    DECODE_PRIMARY = "decode_primary"
    DECODE_FALLBACK = "decode_fallback"
    CLEANUP = "cleanup"


class JobStatus(str, Enum):
    """Status of a job in the queue."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobDoc(MongoBaseModel):
    """
    MongoDB document for a job in the processing queue.

    Collection: jobs

    Uses a simple polling-based queue pattern suitable for low-volume workloads.
    """

    # Job identification
    job_id: str = Field(..., description="Unique job identifier (UUID)")
    job_type: JobType = Field(..., description="Type of processing job")

    # Target
    image_id: str = Field(..., description="Image to process")
    batch_id: str = Field(..., description="Batch for easier querying")

    # Status
    status: JobStatus = Field(default=JobStatus.PENDING)
    priority: int = Field(default=0, description="Higher = more urgent")

    # Execution tracking
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    worker_id: str | None = Field(None, description="ID of worker processing this job")
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Results
    result: dict[str, Any] | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None

    # Scheduling
    scheduled_for: datetime = Field(
        default_factory=utc_now, description="When job should be processed"
    )
    locked_until: datetime | None = Field(None, description="Lock expiry for in-progress jobs")

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.attempt_count < self.max_attempts

    def start(self, worker_id: str, lock_duration_seconds: int = 300) -> None:
        """Mark job as started by a worker."""
        from datetime import timedelta

        now = utc_now()
        self.status = JobStatus.IN_PROGRESS
        self.worker_id = worker_id
        self.started_at = now
        self.attempt_count += 1
        self.locked_until = now + timedelta(seconds=lock_duration_seconds)
        self.updated_at = now

    def complete(self, result: dict[str, Any] | None = None) -> None:
        """Mark job as completed."""
        now = utc_now()
        self.status = JobStatus.COMPLETED
        self.completed_at = now
        self.result = result
        self.locked_until = None
        self.updated_at = now

    def fail(self, error_message: str, error_details: dict[str, Any] | None = None) -> None:
        """Mark job as failed."""
        now = utc_now()
        self.error_message = error_message
        self.error_details = error_details
        self.locked_until = None
        self.updated_at = now

        if self.can_retry():
            # Reset to pending for retry
            self.status = JobStatus.PENDING
            self.worker_id = None
        else:
            self.status = JobStatus.FAILED
            self.completed_at = now

    def cancel(self) -> None:
        """Cancel the job."""
        now = utc_now()
        self.status = JobStatus.CANCELLED
        self.completed_at = now
        self.locked_until = None
        self.updated_at = now
