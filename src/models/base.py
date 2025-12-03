"""
Common base models and utilities.
"""

from datetime import datetime, timezone
from typing import Annotated, Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic v2."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any, handler) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            if ObjectId.is_valid(v):
                return ObjectId(v)
        raise ValueError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema_generator, _field_schema):
        return {"type": "string"}


# Annotated type for ObjectId fields
ObjectIdField = Annotated[PyObjectId | None, Field(default=None, alias="_id")]


class MongoBaseModel(BaseModel):
    """Base model for MongoDB documents."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )

    id: ObjectIdField = None

    @field_validator("id", mode="before")
    @classmethod
    def validate_object_id(cls, v: Any) -> ObjectId | None:
        if v is None:
            return None
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")

    @field_serializer("id")
    def serialize_object_id(self, v: ObjectId | None) -> str | None:
        return str(v) if v else None

    def to_mongo(self) -> dict[str, Any]:
        """Convert model to MongoDB document format."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "id" in data and data["id"] is None:
            del data["id"]
        return data

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> "MongoBaseModel":
        """Create model from MongoDB document."""
        if data is None:
            raise ValueError("Cannot create model from None")
        return cls(**data)


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)
