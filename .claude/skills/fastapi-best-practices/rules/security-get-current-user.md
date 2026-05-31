---
title: Resolve the Current User in a Dependency
impact: CRITICAL
impactDescription: one reusable auth gate; handlers receive a validated user, not a raw token
tags: fastapi, security, get_current_user, depends, annotated, authentication
---

## Resolve the Current User in a Dependency

Turn the raw token into a validated user object inside a `get_current_user` dependency, then
depend on *that* in your handlers. Authentication logic (decode token, look up user, raise
`401`) lives in one place, and every protected endpoint receives a typed user instead of
repeating token-validation code.

**Incorrect (each handler re-validates the token):**

```python
@router.get("/me")
async def me(token: Annotated[str, Depends(oauth2_scheme)]):
    user = decode_and_lookup(token)        # repeated in every handler
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
```

**Correct (auth gate factored into a dependency):**

```python
from typing import Annotated
from fastapi import Depends, HTTPException


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    user = decode_and_lookup(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return user
```

See https://fastapi.tiangolo.com/tutorial/security/get-current-user/
