---
title: Use response_model_exclude_unset for Partial Data
impact: MEDIUM
impactDescription: responses omit fields the client never set, instead of echoing defaults
tags: fastapi, response_model_exclude_unset, partial, defaults, pydantic
---

## Use response_model_exclude_unset for Partial Data

When a stored object only has some fields populated, `response_model_exclude_unset=True`
returns just the fields that were explicitly set, rather than padding the response with model
defaults the caller never provided. Useful for PATCH-style reads and sparse database rows.

**Incorrect (defaults leak into the response):**

```python
class Item(BaseModel):
    name: str
    description: str | None = None
    tax: float = 10.5
    tags: list[str] = []


@router.get("/items/{item_id}", response_model=Item)
async def read_item(item_id: str):
    return items[item_id]  # response always includes tax=10.5, tags=[], description=null
```

**Correct (only the fields actually set are returned):**

```python
@router.get(
    "/items/{item_id}",
    response_model=Item,
    response_model_exclude_unset=True,
)
async def read_item(item_id: str):
    return items[item_id]  # {"name": "Foo", "price": 50.2} if only those were set
```

Related parameters: `response_model_exclude_none`, `response_model_exclude`,
`response_model_include`.

See https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_unset
