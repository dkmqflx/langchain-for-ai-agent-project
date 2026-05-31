---
title: Manage Startup/Shutdown With the lifespan Context Manager
impact: MEDIUM
impactDescription: modern, non-deprecated lifecycle hooks; setup and teardown in one place
tags: fastapi, lifespan, asynccontextmanager, startup, shutdown, on_event, deprecated
---

## Manage Startup/Shutdown With the lifespan Context Manager

Run startup and shutdown logic through the `lifespan` async context manager passed to
`FastAPI(lifespan=...)`. Code before `yield` runs at startup, code after `yield` at shutdown.
The older `@app.on_event("startup")` / `@app.on_event("shutdown")` decorators are deprecated —
don't use them.

**Incorrect (deprecated event decorators):**

```python
@app.on_event("startup")
async def startup():
    build_index()


@app.on_event("shutdown")
async def shutdown():
    cleanup()
```

**Correct (lifespan context manager):**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    build_index()      # startup
    yield
    cleanup()          # shutdown


app = FastAPI(lifespan=lifespan)
```

`backend/main.py` already uses this pattern to build the BM25 index at startup.

See https://fastapi.tiangolo.com/advanced/events/
