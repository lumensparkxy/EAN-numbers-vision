"""
MongoDB client and connection management.
"""

import warnings
from functools import lru_cache
from typing import Any

from pymongo import MongoClient # type: ignore
from pymongo.database import Database # type: ignore

from src.config import get_settings


_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Get or create MongoDB client."""
    global _client
    if _client is None:
        settings = get_settings()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*CosmosDB.*")
            _client = MongoClient(
                settings.mongodb_uri_str,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=30000,
                retryWrites=True,
                w="majority",
            )
    return _client


def get_database() -> Database[dict[str, Any]]:
    """Get the configured MongoDB database."""
    settings = get_settings()
    client = get_client()
    return client[settings.mongodb_database]


def close_client() -> None:
    """Close MongoDB client connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


@lru_cache
def get_collection_names() -> dict[str, str]:
    """Get collection names for the application."""
    return {
        "images": "images",
        "detections": "detections",
        "products": "products",
        "jobs": "jobs",
    }
