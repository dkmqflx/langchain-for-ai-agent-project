---
title: Load Expensive Resources Once at Startup
impact: MEDIUM
impactDescription: heavy models/connections loaded a single time, not per request
tags: fastapi, lifespan, startup, ml-model, connection-pool, performance, caching
---

## Load Expensive Resources Once at Startup

Load costly resources — ML models, search indexes, connection pools — once in the `lifespan`
startup phase and reuse them across requests. Loading them inside a handler repeats the cost
on every request; loading them at import time runs during tests and tooling. The lifespan runs
exactly once, after import, before serving.

**Incorrect (reloaded on every request):**

```python
@router.post("/predict")
async def predict(x: float):
    model = load_model_from_disk()    # expensive disk read per request
    return {"result": model(x)}
```

**Correct (loaded once at startup, reused):**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

ml_models = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    ml_models["predictor"] = load_model_from_disk()   # once
    yield
    ml_models.clear()


app = FastAPI(lifespan=lifespan)


@router.post("/predict")
async def predict(x: float):
    return {"result": ml_models["predictor"](x)}
```

See https://fastapi.tiangolo.com/advanced/events/
