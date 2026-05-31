---
title: Validate With Pydantic, Not Manual Checks
impact: HIGH
impactDescription: declarative validation, automatic 422 errors, self-documenting constraints
tags: fastapi, pydantic, validation, field, literal, 422
---

## Validate With Pydantic, Not Manual Checks

Express input constraints on the Pydantic model with type hints, `Field(...)`, and `Literal`
instead of hand-writing `if` checks inside the handler. FastAPI validates the body before the
handler runs, returns a structured `422` automatically, and surfaces every constraint in the
OpenAPI schema.

**Incorrect (manual validation in the handler):**

```python
@router.post("/refund")
async def refund(req: dict):
    if "decision" not in req or req["decision"] not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="bad decision")
    if req.get("amount", 0) <= 0:
        raise HTTPException(status_code=400, detail="bad amount")
    ...
```

**Correct (declarative — FastAPI enforces it):**

```python
from typing import Literal
from pydantic import BaseModel, Field


class RefundRequest(BaseModel):
    decision: Literal["approve", "reject"]
    amount: float = Field(gt=0)


@router.post("/refund")
async def refund(req: RefundRequest):
    ...
```

The `Literal["approve", "reject"]` field in `backend/models/refund.py` is a good example.

See https://fastapi.tiangolo.com/tutorial/body-fields/
