---
title: Protect Route Groups With Router Dependencies
impact: HIGH
impactDescription: auth enforced on every route in a group; impossible to forget on a new one
tags: fastapi, security, apirouter, dependencies, authorization, depends
---

## Protect Route Groups With Router Dependencies

When every endpoint in a router needs authentication, declare the dependency once on the
`APIRouter` (or the `include_router` call) instead of repeating it on each path operation.
Router-level dependencies run before every operation, so a newly added route is protected by
default — you can't forget to guard it.

**Incorrect (auth repeated, easy to omit on a new route):**

```python
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(user: CurrentUser):  # remember this on every handler...
    ...


@router.get("/stats")
async def stats():  # oops — forgot the dependency, this route is unprotected
    ...
```

**Correct (one gate for the whole group):**

```python
from fastapi import APIRouter, Depends

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/users")
async def list_users():  # protected automatically
    ...


@router.get("/stats")
async def stats():       # also protected — nothing to forget
    ...
```

The return value of a router-level dependency isn't injected; if a handler needs the user
object, also declare `CurrentUser` in its signature.

See https://fastapi.tiangolo.com/tutorial/bigger-applications/
