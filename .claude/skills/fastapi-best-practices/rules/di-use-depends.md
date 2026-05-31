---
title: Share Logic With Depends, Not Manual Instantiation
impact: HIGH
impactDescription: reusable, testable, override-able dependencies; less repetition
tags: fastapi, depends, dependency-injection, reuse, testing, overrides
---

## Share Logic With Depends, Not Manual Instantiation

Declare shared setup (DB sessions, the current user, common query params, configured clients)
as a dependency function and inject it with `Depends()`. FastAPI resolves it per request,
caches it within the request, exposes it in OpenAPI, and lets tests override it. Calling
helper functions directly inside the handler hides those requirements and can't be overridden.

**Incorrect (manual resolution inside the handler):**

```python
@router.get("/items/")
async def read_items(skip: int = 0, limit: int = 100):
    db = get_db_connection()        # invisible dependency, not override-able in tests
    return db.query(skip, limit)
```

**Correct (declared dependency):**

```python
from typing import Annotated
from fastapi import Depends


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/items/")
async def read_items(db: Annotated[Session, Depends(get_db)], skip: int = 0):
    return db.query(skip)
```

In tests, override with `app.dependency_overrides[get_db] = fake_db`.

See https://fastapi.tiangolo.com/tutorial/dependencies/
