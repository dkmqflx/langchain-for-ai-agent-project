---
title: Validate Query Parameters With Annotated[..., Query()]
impact: HIGH
impactDescription: automatic 422 on bad input, constraints documented in OpenAPI
tags: fastapi, query, validation, annotated, min_length, max_length, pattern
---

## Validate Query Parameters With Annotated[..., Query()]

Attach validation and metadata to query parameters with `Annotated[T, Query(...)]`:
`min_length`, `max_length`, `pattern`, `title`, `description`, `alias`. FastAPI enforces the
constraints, returns a structured `422` on violation, and documents them. Put the real Python
default after the `=`, not inside `Query()`.

**Incorrect (no constraints, manual checks in the handler):**

```python
@router.get("/items/")
async def read_items(q: str | None = None):
    if q is not None and len(q) > 50:
        raise HTTPException(status_code=400, detail="q too long")
    ...
```

**Correct (declarative validation):**

```python
from typing import Annotated
from fastapi import Query


@router.get("/items/")
async def read_items(
    q: Annotated[str | None, Query(min_length=3, max_length=50)] = None,
):
    ...
```

Required (no default): `q: Annotated[str, Query(min_length=3)]`. Repeatable list param:
`q: Annotated[list[str] | None, Query()] = None` accepts `?q=a&q=b`.

See https://fastapi.tiangolo.com/tutorial/query-params-str-validations/
