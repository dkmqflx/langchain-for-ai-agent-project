---
title: Use httpx AsyncClient for Async Tests
impact: MEDIUM
impactDescription: lets a test await real async I/O (DB, agents) alongside the request
tags: fastapi, testing, async, httpx, asyncclient, asgitransport, anyio, pytest
---

## Use httpx AsyncClient for Async Tests

`TestClient` runs synchronously, so it can't be used from an `async def` test. When a test
needs to `await` async work itself — an async DB query, an agent call — drive the app with
`httpx.AsyncClient` over `ASGITransport`, marked with `@pytest.mark.anyio`.

**Wrong (TestClient inside an async test):**

```python
@pytest.mark.anyio
async def test_root():
    response = client.get("/")          # sync client in an async test — breaks
    ...
```

**Correct (AsyncClient + ASGITransport):**

```python
import pytest
from httpx import ASGITransport, AsyncClient
from .main import app


@pytest.mark.anyio
async def test_root():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/")
    assert response.status_code == 200
```

Note: `AsyncClient` does not trigger lifespan events; use `asgi-lifespan`'s `LifespanManager`
if your test depends on startup resources.

See https://fastapi.tiangolo.com/advanced/async-tests/
