---
title: Test Endpoints With TestClient
impact: HIGH
impactDescription: fast, in-process HTTP tests asserting status codes and JSON
tags: fastapi, testing, testclient, pytest, httpx, integration-test
---

## Test Endpoints With TestClient

Test path operations through `fastapi.testclient.TestClient`, which drives the app in-process
over real HTTP semantics (built on HTTPX). Write plain `def test_*` functions, call
`client.get/post(...)`, and assert on `response.status_code` and `response.json()`. This
exercises routing, validation, serialization, and error handling end to end — far more than
calling the handler function directly.

**Weak (calls the function, skips routing/validation/serialization):**

```python
def test_read_item():
    result = read_item("foo")        # bypasses the whole FastAPI stack
    assert result["id"] == "foo"
```

**Correct (real request through the app):**

```python
from fastapi.testclient import TestClient
from .main import app

client = TestClient(app)


def test_read_item():
    response = client.get("/items/foo")
    assert response.status_code == 200
    assert response.json() == {"id": "foo", "title": "Foo"}


def test_read_item_missing():
    response = client.get("/items/nope")
    assert response.status_code == 404
```

Requires `httpx` and `pytest`. Send a JSON body with `json=...`, headers with `headers=...`.

See https://fastapi.tiangolo.com/tutorial/testing/
