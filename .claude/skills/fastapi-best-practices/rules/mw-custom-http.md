---
title: Add Cross-Cutting Behavior With HTTP Middleware
impact: MEDIUM
impactDescription: one place for timing, request IDs, logging across every endpoint
tags: fastapi, middleware, http, call_next, request-id, logging, headers
---

## Add Cross-Cutting Behavior With HTTP Middleware

For behavior that must wrap *every* request — timing, request IDs, access logging, response
headers — use `@app.middleware("http")` rather than copying code into each handler. The
middleware runs code before `call_next(request)` (request phase) and after it (response phase).
Always return the response from `call_next`.

**Incorrect (per-handler timing, repeated everywhere):**

```python
@router.get("/items/")
async def read_items():
    start = time.perf_counter()
    result = do_work()
    print("took", time.perf_counter() - start)   # duplicated in every handler
    return result
```

**Correct (one middleware for all routes):**

```python
import time
from fastapi import FastAPI, Request

app = FastAPI()


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.perf_counter() - start)
    return response
```

Middleware added later is outermost (runs first on the request, last on the response). For a
custom response header the browser must read, also list it in CORS `expose_headers`.

See https://fastapi.tiangolo.com/tutorial/middleware/
