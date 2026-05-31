---
title: Document Non-200 Responses in OpenAPI
impact: LOW
impactDescription: error shapes (404, 422) appear in the docs and generated clients
tags: fastapi, openapi, responses, documentation, error-model, 404
---

## Document Non-200 Responses in OpenAPI

By default only the success response is described in the schema. Declare the other status
codes an endpoint can return — `404`, `403`, `409` — via the `responses=` parameter, each with
a model and description. Consumers and generated client SDKs then know the error shape, not
just the happy path.

**Undocumented (clients don't know the 404 shape):**

```python
@router.get("/items/{item_id}", response_model=Item)
async def read_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]
```

**Documented (404 model shows up in OpenAPI):**

```python
class Message(BaseModel):
    detail: str


@router.get(
    "/items/{item_id}",
    response_model=Item,
    responses={404: {"model": Message, "description": "Item not found"}},
)
async def read_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]
```

Define a shared `responses` dict and merge it with `{**common, 404: {...}}` to reuse across
routes.

See https://fastapi.tiangolo.com/advanced/additional-responses/
