---
title: Give Each APIRouter a prefix and tags
impact: HIGH
impactDescription: no repeated path prefixes, grouped OpenAPI docs, per-group config in one place
tags: fastapi, apirouter, prefix, tags, routing, openapi, structure
---

## Give Each APIRouter a prefix and tags

Configure the shared path `prefix`, `tags`, and common `responses`/`dependencies` on the
`APIRouter` itself rather than repeating them on every path operation. The prefix is applied
to all routes in the router, tags group them in the OpenAPI docs, and the config lives in one
place. A bare `APIRouter()` pushes all of that into each decorator.

**Incorrect (bare router — prefix repeated, no grouping):**

```python
router = APIRouter()


@router.get("/items/")
async def read_items(): ...


@router.get("/items/{item_id}")
async def read_item(item_id: str): ...
```

**Correct (prefix + tags on the router):**

```python
router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def read_items(): ...


@router.get("/{item_id}")
async def read_item(item_id: str): ...
```

Note: the `prefix` must not end with a trailing `/`.

See https://fastapi.tiangolo.com/tutorial/bigger-applications/
