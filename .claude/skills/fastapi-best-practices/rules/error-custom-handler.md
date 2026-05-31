---
title: Centralize Cross-Cutting Errors in Exception Handlers
impact: MEDIUM
impactDescription: one place for domain-error mapping and a uniform error response shape
tags: fastapi, exception_handler, jsonresponse, error-envelope, dry
---

## Centralize Cross-Cutting Errors in Exception Handlers

For a domain exception that can be raised from many handlers, or to enforce a uniform error
envelope, register an `@app.exception_handler`. The mapping from exception to HTTP response
lives in one place instead of being repeated as `try/except` in every endpoint.

**Repetitive (same translation in every handler):**

```python
@router.get("/a")
async def a():
    try:
        return do_a()
    except ItemNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))  # repeated everywhere
```

**Centralized (one handler for the whole app):**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ItemNotFound(Exception):
    def __init__(self, name: str):
        self.name = name


app = FastAPI()


@app.exception_handler(ItemNotFound)
async def item_not_found_handler(request: Request, exc: ItemNotFound):
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": f"{exc.name} not found", "data": None},
    )
```

`backend/main.py` uses this pattern to wrap all `HTTPException`s in the
`{success, message, data}` envelope.

See https://fastapi.tiangolo.com/tutorial/handling-errors/#install-custom-exception-handlers
