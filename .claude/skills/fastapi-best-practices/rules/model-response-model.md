---
title: Declare a Response Model on Every Endpoint
impact: CRITICAL
impactDescription: validates output, filters sensitive fields, documents the API
tags: fastapi, response_model, pydantic, serialization, openapi, security
---

## Declare a Response Model on Every Endpoint

Declare the response shape with a return-type annotation (or the `response_model=`
parameter). FastAPI then validates the returned data, serializes it via Pydantic, filters
it to exactly the declared fields, and generates the OpenAPI schema. An endpoint with no
declared response shape returns whatever the handler happens to produce — unvalidated and
undocumented.

**Incorrect (returns a raw dict, no validation or schema):**

```python
@router.get("/items/{item_id}")
async def read_item(item_id: str):
    return {"item": items[item_id]}  # shape is whatever this dict is today
```

**Correct (declared model — validated, filtered, documented):**

```python
class Item(BaseModel):
    name: str
    price: float


@router.get("/items/{item_id}")
async def read_item(item_id: str) -> Item:
    return items[item_id]
```

The `{success, message, data}` envelope models in `backend/models/upload.py`
(`UploadResponse`, `DocumentsResponse`) are good examples of declared response models.

See https://fastapi.tiangolo.com/tutorial/response-model/
