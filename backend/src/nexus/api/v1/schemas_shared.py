from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FilterCondition(BaseModel):
    field: str
    op: str
    value: Any
    value2: Any | None = None


class FilterGroup(BaseModel):
    logic: str = "and"
    conditions: list[FilterCondition] = []
    groups: list[FilterGroup] = []


class SortItem(BaseModel):
    field: str
    dir: str = "asc"


class SavedViewInput(BaseModel):
    name: str
    entity: str
    columns: list[str] = []
    sort: list[SortItem] = []
    filters: list[dict[str, Any]] = []
