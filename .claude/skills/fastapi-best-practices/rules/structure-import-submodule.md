---
title: Import the Router Submodule, Not the router Variable
impact: MEDIUM
impactDescription: avoids name collisions that silently drop entire routers
tags: fastapi, imports, apirouter, include_router, namespacing, structure
---

## Import the Router Submodule, Not the router Variable

Every router module conventionally names its router `router`. If you import the `router`
variable from several modules, the last import shadows the earlier ones and those routers
silently vanish. Import the *submodule* and reference `module.router` instead.

**Incorrect (second import overwrites the first):**

```python
from .routers.items import router   # bound to name `router`
from .routers.users import router   # rebinds `router` — items' router is lost

app.include_router(router)          # only users is registered
app.include_router(router)          # registers users twice
```

**Correct (submodule keeps each router distinct):**

```python
from .routers import items, users

app.include_router(items.router)
app.include_router(users.router)
```

See https://fastapi.tiangolo.com/tutorial/bigger-applications/
