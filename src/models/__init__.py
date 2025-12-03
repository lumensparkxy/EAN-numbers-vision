"""
Pydantic models for MongoDB documents and API schemas.
"""

from src.models.detection import (
    DetectionDoc,
    DetectionSource,
)
from src.models.image import (
    ImageDoc,
    ImageStatus,
    PreprocessingInfo,
    ProcessingInfo,
)
from src.models.job import JobDoc, JobStatus, JobType
from src.models.product import ProductDoc

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
