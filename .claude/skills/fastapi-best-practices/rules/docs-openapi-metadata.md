---
title: Add summary, description, and tags Metadata
impact: LOW
impactDescription: readable, grouped, self-describing API docs for consumers
tags: fastapi, openapi, documentation, summary, description, tags, response_description
---

## Add summary, description, and tags Metadata

Lift the quality of the auto-generated docs with metadata: `tags` to group operations,
`summary` and `description` (or a docstring) to explain them, and `response_description` for
the success response. This is nearly free and makes `/docs` usable by other teams.

**Bare (operation has no human-facing description):**

```python
@router.post("/items/", response_model=Item)
async def create_item(item: Item):
    return item
```

**Documented (grouped and described):**

```python
@router.post(
    "/items/",
    response_model=Item,
    tags=["items"],
    summary="Create an item",
    response_description="The created item",
)
async def create_item(item: Item):
    """Create an item with all the information: name, price, and optional tags."""
    return item
```

`tags` are usually set once on the `APIRouter` (see `structure-apirouter-prefix-tags`); set
per-operation metadata where it adds clarity.

See https://fastapi.tiangolo.com/tutorial/path-operation-configuration/
