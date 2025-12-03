"""
Database initialization script - creates indexes and validates connection.
"""

import sys

import structlog

from src.config import get_settings
from src.db.client import get_database, close_client
from src.db.repositories.images import ImageRepository
from src.db.repositories.detections import DetectionRepository
from src.db.repositories.products import ProductRepository
from src.db.repositories.jobs import JobRepository


logger = structlog.get_logger(__name__)


def init_indexes() -> None:
    """Initialize all collection indexes."""
    settings = get_settings()
    logger.info(
        "Initializing database indexes",
        database=settings.mongodb_database,
        environment=settings.environment,
    )

    try:
        db = get_database()

        # Test connection
        db.command("ping")
        logger.info("Database connection successful")

        # Create indexes for each collection
        collections = [
            ("images", ImageRepository),
            ("detections", DetectionRepository),
            ("products", ProductRepository),
            ("jobs", JobRepository),
        ]

        for collection_name, repo_class in collections:
            collection = db[collection_name]
            indexes = repo_class.create_indexes(collection)
            logger.info(
                f"Created indexes for {collection_name}",
                collection=collection_name,
                indexes=indexes,
            )

        logger.info("All indexes created successfully")

    except Exception as e:
        logger.error("Failed to initialize indexes", error=str(e))
        raise
    finally:
        close_client()


def main() -> None:
    """Main entry point."""
    try:
        init_indexes()
        print("Database indexes initialized successfully!")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
