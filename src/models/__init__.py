"""
Pydantic models for MongoDB documents and API schemas.
"""

from src.models.image import (
    ImageDoc,
    ImageStatus,
    PreprocessingInfo,
    ProcessingInfo,
)
from src.models.detection import (
    DetectionDoc,
    DetectionSource,
)
from src.models.product import ProductDoc
from src.models.job import JobDoc, JobStatus, JobType

__all__ = [
    # Image
    "ImageDoc",
    "ImageStatus",
    "PreprocessingInfo",
    "ProcessingInfo",
    # Detection
    "DetectionDoc",
    "DetectionSource",
    # Product
    "ProductDoc",
    # Job
    "JobDoc",
    "JobStatus",
    "JobType",
]
