"""
Job dispatcher - coordinates processing pipeline.

Monitors image statuses and dispatches jobs to workers:
- Pending images → Preprocess jobs
- Preprocessed images (no fallback) → Primary decode jobs
- Images needing fallback → Fallback decode jobs
"""

import time
from datetime import datetime

import structlog

from src.config import get_settings
from src.db import get_database, ImageRepository, JobRepository
from src.models import ImageStatus, JobType


logger = structlog.get_logger(__name__)


class JobDispatcher:
    """
    Dispatches jobs based on image status.

    Implements a simple polling-based job queue pattern.
    """

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self.db = get_database()
        self.image_repo = ImageRepository(self.db)
        self.job_repo = JobRepository(self.db)

    def dispatch_preprocess_jobs(self) -> int:
        """
        Find pending images and create preprocess jobs.

        Returns:
            Number of jobs created
        """
        pending = self.image_repo.find_by_status(
            ImageStatus.PENDING,
            limit=self.batch_size,
        )

        created = 0
        for image in pending:
            # Check if job already exists
            if not self.job_repo.exists_for_image(image.image_id, JobType.PREPROCESS):
                self.job_repo.enqueue(
                    job_type=JobType.PREPROCESS,
                    image_id=image.image_id,
                    batch_id=image.batch_id,
                )
                created += 1

        if created > 0:
            logger.info("Created preprocess jobs", count=created)

        return created

    def dispatch_primary_decode_jobs(self) -> int:
        """
        Find preprocessed images and create primary decode jobs.

        Returns:
            Number of jobs created
        """
        preprocessed = self.image_repo.find_by_status(
            ImageStatus.PREPROCESSED,
            limit=self.batch_size,
        )

        # Filter out images that already need fallback
        eligible = [
            img for img in preprocessed
            if not img.processing.needs_fallback
        ]

        created = 0
        for image in eligible:
            if not self.job_repo.exists_for_image(image.image_id, JobType.DECODE_PRIMARY):
                self.job_repo.enqueue(
                    job_type=JobType.DECODE_PRIMARY,
                    image_id=image.image_id,
                    batch_id=image.batch_id,
                )
                created += 1

        if created > 0:
            logger.info("Created primary decode jobs", count=created)

        return created

    def dispatch_fallback_jobs(self) -> int:
        """
        Find images needing fallback and create fallback decode jobs.

        Returns:
            Number of jobs created
        """
        fallback_images = self.image_repo.find_needing_fallback(
            limit=self.batch_size,
        )

        created = 0
        for image in fallback_images:
            if not self.job_repo.exists_for_image(image.image_id, JobType.DECODE_FALLBACK):
                self.job_repo.enqueue(
                    job_type=JobType.DECODE_FALLBACK,
                    image_id=image.image_id,
                    batch_id=image.batch_id,
                )
                created += 1

        if created > 0:
            logger.info("Created fallback decode jobs", count=created)

        return created

    def run_dispatch_cycle(self) -> dict[str, int]:
        """
        Run a full dispatch cycle.

        Returns:
            Dictionary of job counts by type
        """
        results = {
            "preprocess": self.dispatch_preprocess_jobs(),
            "primary_decode": self.dispatch_primary_decode_jobs(),
            "fallback_decode": self.dispatch_fallback_jobs(),
        }
        return results

    def get_stats(self) -> dict[str, any]:
        """Get current pipeline statistics."""
        image_stats = self.image_repo.get_stats()
        
        # Get counts for pending work (what workers will process)
        pending_work = {
            "pending_preprocess": len(self.image_repo.find_pending(limit=10000)),
            "pending_primary_decode": len(self.image_repo.find_preprocessed(limit=10000)),
            "pending_fallback_decode": len(self.image_repo.find_needing_fallback(limit=10000)),
        }

        return {
            "images": image_stats,
            "pending_work": pending_work,
            "timestamp": datetime.utcnow().isoformat(),
        }


def main():
    """Main entry point for dispatcher."""
    import argparse

    parser = argparse.ArgumentParser(description="Job Dispatcher")
    parser.add_argument("--batch-size", type=int, default=50, help="Max jobs per dispatch")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between dispatches")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--stats", action="store_true", help="Print stats and exit")
    args = parser.parse_args()

    dispatcher = JobDispatcher(batch_size=args.batch_size)

    if args.stats:
        import json
        stats = dispatcher.get_stats()
        print(json.dumps(stats, indent=2, default=str))
        return

    logger.info("Starting job dispatcher", batch_size=args.batch_size)

    while True:
        try:
            results = dispatcher.run_dispatch_cycle()
            total_dispatched = sum(results.values())

            if total_dispatched > 0:
                logger.info("Dispatch cycle complete", **results)

        except Exception as e:
            logger.error("Dispatcher error", error=str(e))

        if args.once:
            break

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
