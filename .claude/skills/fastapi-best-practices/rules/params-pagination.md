---
title: Paginate List Endpoints With Bounded limit/offset
impact: MEDIUM
impactDescription: bounded result size protects the server; empty list, not 404, for no rows
tags: fastapi, pagination, limit, offset, list, query, field
---

## Paginate List Endpoints With Bounded limit/offset

A list endpoint should never return an unbounded result set. Accept `limit` and `offset`
query parameters with an upper bound on `limit` (via `Field`/`Query`), and return an empty
list — not a `404` — when there are no matching rows. `404` means the *collection* itself
doesn't exist; an empty collection is a successful `200` with `[]`.

**Incorrect (unbounded, and 404 on no results):**

```python
@router.get("/items/")
async def list_items():
    items = db.all()            # could be millions of rows
    if not items:
        raise HTTPException(status_code=404, detail="no items")  # wrong — [] is valid
    return items
```

**Correct (bounded page, empty list is a 200):**

```python
from typing import Annotated
from fastapi import Query


@router.get("/items/")
async def list_items(
    limit: Annotated[int, Query(gt=0, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Item]:
    return db.page(limit=limit, offset=offset)   # [] when empty, that's fine
```

For richer paging, group the params with a query-parameter model (see
`params-query-param-models`) and consider returning a `{items, total, limit, offset}` envelope.

See https://fastapi.tiangolo.com/tutorial/query-params-str-validations/
