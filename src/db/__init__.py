"""
Database layer for MongoDB operations.
"""

from src.db.client import close_client, get_client, get_database
from src.db.repositories import (
    DetectionRepository,
    ImageRepository,
    JobRepository,
    ProductRepository,
)

__all__ = [
    "get_database",
    "get_client",
    "close_client",
    "ImageRepository",
    "DetectionRepository",
    "ProductRepository",
    "JobRepository",
]
