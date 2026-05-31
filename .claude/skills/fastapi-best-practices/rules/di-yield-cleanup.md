---
title: Use Dependencies With yield for Setup/Teardown
impact: HIGH
impactDescription: resources (DB sessions, files) always released, even when the handler errors
tags: fastapi, depends, yield, cleanup, teardown, database, session, resource
---

## Use Dependencies With yield for Setup/Teardown

For a resource that must be opened then reliably closed — a database session, a file handle,
a network client — use a dependency with `yield`. FastAPI runs the code before `yield` to set
up, injects the yielded value, and runs the code after `yield` to tear down once the response
is sent, even if the path operation raised. This beats opening/closing by hand in each handler.

**Incorrect (manual lifecycle, leaks on error):**

```python
@router.get("/items/")
async def read_items():
    db = SessionLocal()
    items = db.query(...)   # if this raises, db is never closed
    db.close()
    return items
```

**Correct (yield dependency guarantees cleanup):**

```python
from typing import Annotated
from fastapi import Depends


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()          # runs after the response, even on error


@router.get("/items/")
async def read_items(db: Annotated[Session, Depends(get_db)]):
    return db.query(...)
```

See https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
