---
title: Use Specific Status Codes, Not a Blanket 500
impact: HIGH
impactDescription: clients can react correctly (retry, fix input, re-auth); honest API
tags: fastapi, status-code, http, 404, 400, 409, 401, error-handling
---

## Use Specific Status Codes, Not a Blanket 500

Map each failure to the status code that describes it: `404` for a missing resource, `400`
for invalid input, `409` for a conflicting state, `401`/`403` for auth. A `500` means "the
server broke" — using it for client-side problems misleads callers and hides real bugs.

**Incorrect (everything is a 500):**

```python
@router.post("/approve")
async def approve(refund_id: str):
    req = lookup(refund_id)
    if req is None:
        raise HTTPException(status_code=500, detail="not found")     # really a 404
    if req.status != "pending":
        raise HTTPException(status_code=500, detail="already done")  # really a 409
    ...
```

**Correct (the code matches the cause):**

```python
@router.post("/approve")
async def approve(refund_id: str):
    req = lookup(refund_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Refund not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Refund already processed")
    ...
```

`backend/routers/refund.py` models this well (`404` for missing, `400` for bad state).

See https://fastapi.tiangolo.com/tutorial/handling-errors/
