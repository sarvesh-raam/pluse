from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T", bound=BaseModel)


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-indexed page number"),
        size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    ):
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int
    pages: int


def apply_sort(stmt: Select, model, sort: str | None, order: str, default_field: str = "created_at") -> Select:
    field_name = sort if sort and hasattr(model, sort) else default_field
    if not hasattr(model, field_name):
        return stmt
    column = getattr(model, field_name)
    return stmt.order_by(column.desc() if order == "desc" else column.asc())


async def paginate(
    db: AsyncSession, stmt: Select, params: PaginationParams, schema: type[T]
) -> Page[T]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = await db.scalar(count_stmt)
    result = await db.execute(stmt.offset(params.offset).limit(params.size))
    items = [schema.model_validate(row) for row in result.scalars().all()]
    pages = (total + params.size - 1) // params.size if params.size and total else 0
    return Page[T](items=items, page=params.page, size=params.size, total=total or 0, pages=pages)
