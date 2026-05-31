---
title: Stream Long Responses Instead of Buffering
impact: MEDIUM
impactDescription: first byte reaches the client immediately; constant memory for big/LLM output
tags: fastapi, streaming, streamingresponse, sse, generator, async, llm, chat
---

## Stream Long Responses Instead of Buffering

For responses produced incrementally — LLM/agent token streams, large exports, server-sent
events — stream them with `StreamingResponse` and a generator instead of building the whole
body in memory and returning it at once. The client sees output as it's produced, and server
memory stays flat. Yield from an `async` generator and `await` inside it so the stream can be
cancelled when the client disconnects.

**Incorrect (buffer everything, then return):**

```python
@router.post("/chat")
async def chat(req: ChatRequest):
    chunks = []
    async for token in agent.astream(req.message):
        chunks.append(token)          # nothing reaches the client until fully done
    return {"response": "".join(chunks)}
```

**Correct (stream as tokens are produced):**

```python
from fastapi.responses import StreamingResponse


@router.post("/chat")
async def chat(req: ChatRequest):
    async def token_stream():
        async for token in agent.astream(req.message):
            yield token               # flushed to the client immediately

    return StreamingResponse(token_stream(), media_type="text/plain")
```

For an SSE event protocol (`data:` frames, `text/event-stream`), use FastAPI's Server-Sent
Events support or a library like `sse-starlette`'s `EventSourceResponse`.

See https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
