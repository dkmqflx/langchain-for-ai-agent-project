---
title: await Every Async Call
impact: HIGH
impactDescription: prevents un-awaited coroutines that silently return nothing / never run
tags: fastapi, async, await, coroutine, asyncio, bug
---

## await Every Async Call

A coroutine doesn't run until it's awaited. Calling an async function without `await` returns
a coroutine object — the work never happens, and you operate on the wrong value. Inside an
`async def` handler, `await` every async call: async I/O, `UploadFile.read()`,
`agent.ainvoke()`, async DB queries.

**Incorrect (missing await — work never runs):**

```python
@router.post("/upload")
async def upload(file: UploadFile):
    content = file.read()        # a coroutine, not the bytes
    save(content)                # saves a coroutine object — broken
```

**Correct (await the async calls):**

```python
@router.post("/upload")
async def upload(file: UploadFile):
    content = await file.read()
    save(content)
```

`backend/routers/upload.py` (`await file.read()`) and `chat.py` (`await agent.ainvoke(...)`)
do this correctly.

See https://fastapi.tiangolo.com/async/
