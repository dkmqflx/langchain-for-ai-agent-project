---
title: Re-raise HTTPException in Broad except Blocks
impact: HIGH
impactDescription: deliberate 404/400/409 codes survive instead of collapsing to 500
tags: fastapi, httpexception, except, error-handling, status-code, re-raise
---

## Re-raise HTTPException in Broad except Blocks

A broad `except Exception` that wraps everything in `HTTPException(500)` will also catch the
`HTTPException` you deliberately raised — turning a meaningful `404`/`409` into a generic
`500`. Catch and re-raise `HTTPException` first, then wrap only the truly unexpected errors.

**Incorrect (deliberate codes swallowed):**

```python
@router.post("/upload")
async def upload(file: UploadFile):
    try:
        if not allowed(file):
            raise HTTPException(status_code=400, detail="Unsupported file type")
        return process(file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  # the 400 becomes a 500
```

**Correct (let HTTPException pass through):**

```python
@router.post("/upload")
async def upload(file: UploadFile):
    try:
        if not allowed(file):
            raise HTTPException(status_code=400, detail="Unsupported file type")
        return process(file)
    except HTTPException:
        raise                                       # preserve the intended status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

`backend/routers/upload.py` and `chat.py` already use this `except HTTPException: raise` guard.

See https://fastapi.tiangolo.com/tutorial/handling-errors/
