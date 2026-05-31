---
title: Hoist Repeated Dependencies into a Type Alias
impact: MEDIUM
impactDescription: one definition reused across handlers; change the dep in one place
tags: fastapi, annotated, depends, type-alias, dry, dependency-injection
---

## Hoist Repeated Dependencies into a Type Alias

When the same `Annotated[T, Depends(...)]` appears in many handlers, define it once as a
module-level type alias and reuse the alias. The dependency is declared in a single place,
signatures stay short, and editors still see the full type.

**Repetitive (same Annotated spelled out everywhere):**

```python
@router.get("/items/")
async def read_items(commons: Annotated[dict, Depends(common_parameters)]): ...


@router.get("/users/")
async def read_users(commons: Annotated[dict, Depends(common_parameters)]): ...
```

**Reusable (one alias):**

```python
from typing import Annotated
from fastapi import Depends

CommonsDep = Annotated[dict, Depends(common_parameters)]


@router.get("/items/")
async def read_items(commons: CommonsDep): ...


@router.get("/users/")
async def read_users(commons: CommonsDep): ...
```

This pairs well with auth: `CurrentUser = Annotated[User, Depends(get_current_user)]`.

See https://fastapi.tiangolo.com/tutorial/dependencies/#shortcut
