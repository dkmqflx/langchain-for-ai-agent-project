---
title: Never Call Blocking Code Inside async def
impact: HIGH
impactDescription: one blocking call freezes the whole event loop for all concurrent requests
tags: fastapi, async, blocking, event-loop, threadpool, run_in_executor, performance
---

## Never Call Blocking Code Inside async def

Inside an `async def` handler, every line runs on the event loop. A synchronous call that
blocks — a sync DB driver, `requests`, `time.sleep`, heavy CPU work — freezes the loop and
stalls *every* concurrent request, defeating async entirely. Either move the handler to plain
`def` (threadpool), or offload the blocking call.

**Incorrect (blocking call on the event loop):**

```python
import time


@router.get("/report")
async def report():
    time.sleep(5)              # blocks the loop for 5s — all requests hang
    return build_report()
```

**Correct (offload to a thread so the loop stays free):**

```python
import anyio


@router.get("/report")
async def report():
    return await anyio.to_thread.run_sync(build_report_blocking)
```

Or, if the whole handler is blocking, just declare it with plain `def` and let FastAPI run it
in a threadpool (see `async-def-vs-def`).

See https://fastapi.tiangolo.com/async/#path-operation-functions
