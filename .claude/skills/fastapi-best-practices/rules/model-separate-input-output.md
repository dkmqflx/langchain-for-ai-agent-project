---
title: Separate Input and Output Models
impact: CRITICAL
impactDescription: prevents leaking secrets (passwords, hashes, internal fields) in responses
tags: fastapi, response_model, security, pydantic, password, data-leak
---

## Separate Input and Output Models

Use a different Pydantic model for what comes **in** versus what goes **out**. The official
docs treat this as a security requirement: FastAPI limits and filters the response to the
fields declared in the output model, so a field like `password` that exists on the input
model can never accidentally appear in the response.

**Incorrect (one model — password echoed back to the client):**

```python
class User(BaseModel):
    username: str
    password: str
    email: str


@router.post("/user/")
async def create_user(user: User) -> User:
    return user  # leaks the password
```

**Correct (input has the secret, output does not):**

```python
class UserIn(BaseModel):
    username: str
    password: str
    email: str


class UserOut(BaseModel):
    username: str
    email: str


@router.post("/user/", response_model=UserOut)
async def create_user(user: UserIn):
    return user  # FastAPI filters output to UserOut — password is dropped
```

A clean variant: put shared fields on a `BaseUser`, let `UserIn(BaseUser)` add `password`,
and annotate the return as `BaseUser` — type checkers stay happy and output is still filtered.

See https://fastapi.tiangolo.com/tutorial/response-model/
