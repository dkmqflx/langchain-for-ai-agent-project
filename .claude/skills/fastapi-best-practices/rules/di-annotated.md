---
title: Use Annotated[T, Depends(...)] Syntax
impact: HIGH
impactDescription: correct type info for editors/mypy; reusable across path operations
tags: fastapi, annotated, depends, type-hints, mypy, dependency-injection
---

## Use Annotated[T, Depends(...)] Syntax

Declare dependencies as `Annotated[T, Depends(func)]` rather than the legacy default-value
form `param: T = Depends(func)`. The `Annotated` form (FastAPI 0.95+) keeps the real type
visible to editors and type checkers and can be hoisted into a reusable alias. The official
docs recommend it.

**Incorrect (legacy default-value form):**

```python
@router.get("/items/")
async def read_items(commons: dict = Depends(common_parameters)):
    return commons
```

**Correct (Annotated form):**

```python
from typing import Annotated
from fastapi import Depends


@router.get("/items/")
async def read_items(commons: Annotated[dict, Depends(common_parameters)]):
    return commons
```

Pass the function to `Depends` **without** calling it: `Depends(common_parameters)`, not
`Depends(common_parameters())`.

See https://fastapi.tiangolo.com/tutorial/dependencies/
