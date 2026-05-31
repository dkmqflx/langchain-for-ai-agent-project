---
title: Choose async def vs def by the Library You Call
impact: MEDIUM
impactDescription: keeps the event loop unblocked; correct concurrency under load
tags: fastapi, async, def, concurrency, threadpool, event-loop, blocking
---

## Choose async def vs def by the Library You Call

Pick the path-operation flavor based on the I/O you do. Use `async def` when you `await` an
async library. Use plain `def` when you call a blocking/synchronous library — FastAPI runs
`def` handlers in an external threadpool so they don't block the event loop. If you do no
external I/O, `async def` is fine. When unsure, the official guidance is: use plain `def`.

**Wrong (blocking client inside async def — stalls the event loop):**

```python
@router.get("/")
async def read():
    return blocking_db.query()   # synchronous call blocks every other request
```

**Right (blocking library → plain def, FastAPI uses a threadpool):**

```python
@router.get("/")
def read():
    return blocking_db.query()   # runs in a threadpool, loop stays free
```

**Right (async library → async def with await):**

```python
@router.get("/")
async def read():
    return await async_db.query()
```

The backend's handlers are correctly `async def` because they `await` async I/O
(`agent.ainvoke`, `file.read`).

See https://fastapi.tiangolo.com/async/
