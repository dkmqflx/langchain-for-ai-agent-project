---
title: Extract Bearer Tokens With OAuth2PasswordBearer
impact: CRITICAL
impactDescription: standardized 401 handling, OpenAPI "Authorize" integration, no hand-parsing
tags: fastapi, security, oauth2, bearer, token, authentication, annotated, depends
---

## Extract Bearer Tokens With OAuth2PasswordBearer

Use FastAPI's `OAuth2PasswordBearer` as a dependency to pull the Bearer token from the
`Authorization` header. It returns the token as a `str`, automatically responds `401` when
the header is missing or malformed, and wires the "Authorize" button into the interactive
docs. Don't read `request.headers["Authorization"]` and parse it by hand.

**Incorrect (manual header parsing):**

```python
@router.get("/items/")
async def read_items(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth.removeprefix("Bearer ")
    ...
```

**Correct (declared security dependency):**

```python
from typing import Annotated
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.get("/items/")
async def read_items(token: Annotated[str, Depends(oauth2_scheme)]):
    return {"token": token}
```

`tokenUrl="token"` names the endpoint where clients exchange credentials for a token.

See https://fastapi.tiangolo.com/tutorial/security/first-steps/
