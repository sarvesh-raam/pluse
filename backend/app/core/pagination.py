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
    # Only real table columns are sortable. A bare hasattr() check would also
    # accept relationships, methods and dunder attributes (?sort=queue,
    # ?sort=__init__), which blow up into a 500 when passed to ORDER BY.
    columns = model.__table__.columns
    field_name = sort if sort and sort in columns else default_field
    if field_name not in columns:
        return stmt
    column = getattr(model, field_name)
    # Secondary sort on the primary key keeps pagination stable when many
    # rows share the same value (e.g. a batch with identical created_at).
    return stmt.order_by(column.desc() if order == "desc" else column.asc(), model.id)


async def paginate(
    db: AsyncSession, stmt: Select, params: PaginationParams, schema: type[T]
) -> Page[T]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = await db.scalar(count_stmt)
    result = await db.execute(stmt.offset(params.offset).limit(params.size))
    items = [schema.model_validate(row) for row in result.scalars().all()]
    total = total or 0
    pages = (total + params.size - 1) // params.size if total else 0
    return Page[T](items=items, page=params.page, size=params.size, total=total, pages=pages)
