---
title: Split Bigger Apps into Routers, Models, and Dependencies
impact: HIGH
impactDescription: modular, navigable codebase; routers reusable and independently testable
tags: fastapi, structure, apirouter, include_router, project-layout, packages
---

## Split Bigger Apps into Routers, Models, and Dependencies

Organize a growing app into a package: one module per resource under `routers/`, shared
dependencies in `dependencies.py`, request/response models under `models/`. `main.py` builds
the `FastAPI` app and wires routers in with `include_router`. Each directory needs an
`__init__.py` to be an importable package.

**Recommended layout (official FastAPI structure):**

```
app/
├── __init__.py
├── main.py            # creates FastAPI(), includes routers
├── dependencies.py    # shared Depends() functions
├── models/            # Pydantic request/response models
└── routers/
    ├── __init__.py
    ├── items.py       # router = APIRouter(prefix="/items", ...)
    └── users.py
```

**main.py wires the routers together:**

```python
from fastapi import FastAPI
from .routers import items, users

app = FastAPI()

app.include_router(users.router)
app.include_router(items.router)
```

This matches the `routers/`, `models/`, `agent/`, `rag/` split already used in
`customer-support-agent/backend/`.

See https://fastapi.tiangolo.com/tutorial/bigger-applications/
