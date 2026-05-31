---
title: Constrain Path Parameters With Annotated[..., Path()]
impact: MEDIUM
impactDescription: rejects out-of-range IDs at the edge with a 422, not deep in your code
tags: fastapi, path, validation, annotated, ge, le, gt, lt, numeric
---

## Constrain Path Parameters With Annotated[..., Path()]

Declare numeric bounds on path parameters with `Annotated[int, Path(ge=..., le=...)]` so an
out-of-range value is rejected with a `422` before the handler runs. Use `ge`/`gt`/`le`/`lt`
for the bounds and `title` for docs. Path parameters are always required.

**Incorrect (unbounded, validated by hand):**

```python
@router.get("/items/{item_id}")
async def read_item(item_id: int):
    if item_id < 1:
        raise HTTPException(status_code=400, detail="bad id")
    ...
```

**Correct (bounds in Path()):**

```python
from typing import Annotated
from fastapi import Path


@router.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(title="The item ID", gt=0, le=1000)],
):
    ...
```

See https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/
