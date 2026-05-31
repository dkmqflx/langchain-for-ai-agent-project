---
title: Prefer the Return-Type Annotation Over response_model=
impact: HIGH
impactDescription: editor + mypy type-checking of the handler's return value
tags: fastapi, response_model, type-annotation, mypy, pydantic
---

## Prefer the Return-Type Annotation Over response_model=

Declare the response shape with a return-type annotation (`-> Item`) when the returned type
matches what you want to expose. Editors and type checkers then verify your handler actually
returns that type. Reach for the `response_model=` parameter only when the declared output
must differ from the annotated return type (FastAPI gives `response_model=` priority when
both are present).

**Less ideal (parameter only — return value is untyped to tooling):**

```python
@router.post("/items/", response_model=Item)
async def create_item(item: Item):
    return item
```

**Preferred (return-type annotation — tooling checks the return):**

```python
@router.post("/items/")
async def create_item(item: Item) -> Item:
    return item
```

**When they must differ (use the parameter):**

```python
@router.post("/user/", response_model=UserOut)
async def create_user(user: UserIn) -> Any:
    return user
```

See https://fastapi.tiangolo.com/tutorial/response-model/
