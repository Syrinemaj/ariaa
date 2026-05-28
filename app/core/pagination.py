from typing import Generic, List, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy.orm import Query as SAQuery

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


class PaginationParams:
    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate_query(query: SAQuery, params: PaginationParams) -> tuple[list, int]:
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return items, total


def build_paginated_response(items: list, total: int, params: PaginationParams) -> dict:
    total_pages = max(1, (total + params.page_size - 1) // params.page_size)
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "total_pages": total_pages,
    }
