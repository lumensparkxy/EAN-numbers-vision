"""
Database layer for MongoDB operations.
"""

from src.db.client import get_database, get_client, close_client
from src.db.repositories import (
    ImageRepository,
    DetectionRepository,
    ProductRepository,
    JobRepository,
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
