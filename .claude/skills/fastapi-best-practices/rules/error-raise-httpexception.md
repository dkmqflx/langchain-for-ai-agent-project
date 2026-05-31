---
title: raise HTTPException, Never return an Error
impact: HIGH
impactDescription: correct status codes and short-circuit; no error bodies sent with 200 OK
tags: fastapi, httpexception, raise, error-handling, status-code
---

## raise HTTPException, Never return an Error

Signal an error by raising `HTTPException` — it sets the status code and stops the request
immediately. Returning an error dict sends it with a `200 OK`, so clients can't distinguish
success from failure by status code.

**Incorrect (error returned with 200 OK):**

```python
@router.get("/items/{item_id}")
async def read_item(item_id: str):
    if item_id not in items:
        return {"error": "Item not found"}   # status is 200
    return items[item_id]
```

**Correct (raise — proper status, short-circuits):**

```python
from fastapi import HTTPException


@router.get("/items/{item_id}")
async def read_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]
```

`detail` accepts any JSON-serializable value; add `headers=...` for custom error headers.

See https://fastapi.tiangolo.com/tutorial/handling-errors/
