---
title: Read Config From Env With pydantic-settings
impact: MEDIUM
impactDescription: typed, validated config loaded once; override-able in tests
tags: fastapi, settings, pydantic-settings, basesettings, env, config, lru_cache
---

## Read Config From Env With pydantic-settings

Load configuration through a `BaseSettings` class from `pydantic_settings` instead of scattering
`os.getenv(...)` calls. Settings are typed and validated, missing required values fail loudly
at startup, and exposing them via an `@lru_cache`-d dependency makes config injectable and
override-able in tests.

**Incorrect (ad-hoc, untyped, unvalidated env reads):**

```python
import os

DATABASE_URL = os.getenv("DATABASE_URL")        # None if unset — fails later, mysteriously
ITEMS_PER_USER = int(os.getenv("ITEMS_PER_USER", "50"))
```

**Correct (typed settings + cached dependency):**

```python
from functools import lru_cache
from typing import Annotated
from fastapi import Depends
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str                # required — startup fails if missing
    items_per_user: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()


@router.get("/info")
async def info(settings: Annotated[Settings, Depends(get_settings)]):
    return {"items_per_user": settings.items_per_user}
```

`pydantic-settings` is a separate package (`pip install pydantic-settings`); `.env` loading
needs `python-dotenv`.

See https://fastapi.tiangolo.com/advanced/settings/
