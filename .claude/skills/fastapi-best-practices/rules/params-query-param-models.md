---
title: Group Filter/Sort/Search Params in a Query Model
impact: MEDIUM
impactDescription: reusable, validated filter/sort/search params; rejects unknown params
tags: fastapi, query, pydantic, filter, sort, search, model, annotated
---

## Group Filter/Sort/Search Params in a Query Model

When an endpoint takes several related query parameters — `limit`, `offset`, `order_by`,
`search`, `tags` — group them into a Pydantic model and declare it with
`Annotated[FilterParams, Query()]` (FastAPI 0.115+). The model is reusable across endpoints,
centralizes validation, and with `model_config = {"extra": "forbid"}` rejects unknown query
params instead of silently ignoring them.

**Repetitive (loose, unvalidated params spread across the signature):**

```python
@router.get("/items/")
async def read_items(
    limit: int = 100,
    offset: int = 0,
    order_by: str = "created_at",
    search: str | None = None,
):
    ...
```

**Correct (one validated, reusable model):**

```python
from typing import Annotated, Literal
from fastapi import Query
from pydantic import BaseModel, Field


class ItemFilter(BaseModel):
    model_config = {"extra": "forbid"}

    limit: int = Field(100, gt=0, le=100)
    offset: int = Field(0, ge=0)
    order_by: Literal["created_at", "updated_at"] = "created_at"
    search: str | None = None
    tags: list[str] = []


@router.get("/items/")
async def read_items(filter_query: Annotated[ItemFilter, Query()]):
    ...
```

See https://fastapi.tiangolo.com/tutorial/query-param-models/
