from pydantic import BaseModel, Field

from app.schemas.common import ReadSchema


class StoreBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class StoreRead(ReadSchema, StoreBase):
    pass
