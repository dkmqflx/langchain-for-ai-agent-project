---
title: Swap Dependencies in Tests With dependency_overrides
impact: HIGH
impactDescription: tests run against fakes (DB, auth, settings) without monkeypatching internals
tags: fastapi, testing, dependency_overrides, depends, mocking, fixtures
---

## Swap Dependencies in Tests With dependency_overrides

Replace a dependency in tests via `app.dependency_overrides[real_dep] = fake_dep` instead of
monkeypatching module internals. This is exactly why shared logic belongs in `Depends` (see
`di-use-depends`): the DB session, the current user, or settings can be swapped for a fake at
the boundary, cleanly and reversibly.

**Fragile (patching internals by string path):**

```python
def test_list(monkeypatch):
    monkeypatch.setattr("app.routers.items.get_db", fake_db)   # brittle, path-coupled
    ...
```

**Correct (override the dependency):**

```python
from .main import app
from .dependencies import get_db


def fake_db():
    yield FakeSession()


app.dependency_overrides[get_db] = fake_db


def test_list_items():
    response = client.get("/items/")
    assert response.status_code == 200


# clear afterward so overrides don't leak between tests
app.dependency_overrides.clear()
```

Override `get_current_user` the same way to test protected routes without real tokens.

See https://fastapi.tiangolo.com/advanced/testing-dependencies/
