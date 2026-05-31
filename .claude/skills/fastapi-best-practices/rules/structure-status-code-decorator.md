---
title: Set the Success status_code in the Decorator
impact: MEDIUM
impactDescription: correct HTTP semantics (201 Created) and accurate OpenAPI docs
tags: fastapi, status_code, http, rest, created, decorator, response
---

## Set the Success status_code in the Decorator

Declare the success status code on the path operation decorator. A POST that creates a
resource should return `201 Created`, not the default `200`. Declaring it in the decorator
keeps the OpenAPI docs accurate and avoids hand-building responses just to change the code.
Use `fastapi.status` constants for readability.

**Incorrect (creation returns a bare 200):**

```python
@router.post("/upload")
async def upload_document(file: UploadFile):
    ...
    return result
```

**Correct (explicit 201 for creation):**

```python
from fastapi import status


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile):
    ...
    return result
```

`backend/routers/upload.py` already does this with `status_code=201`.

See https://fastapi.tiangolo.com/tutorial/response-status-code/
