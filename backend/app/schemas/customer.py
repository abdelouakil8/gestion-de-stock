from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ReadSchema


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class CustomerCreate(CustomerBase):
    store_id: UUID


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class CustomerRead(ReadSchema, CustomerBase):
    store_id: UUID
