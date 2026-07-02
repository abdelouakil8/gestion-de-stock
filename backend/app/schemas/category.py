from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ReadSchema


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CategoryCreate(CategoryBase):
    store_id: UUID


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class CategoryRead(ReadSchema, CategoryBase):
    store_id: UUID
