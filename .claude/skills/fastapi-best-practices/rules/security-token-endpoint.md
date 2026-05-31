---
title: Build the Token Endpoint With OAuth2PasswordRequestForm
impact: HIGH
impactDescription: spec-compliant login that works with the docs "Authorize" button and clients
tags: fastapi, security, oauth2, token, password-flow, jwt, request-form, login
---

## Build the Token Endpoint With OAuth2PasswordRequestForm

Implement the login/token route with `OAuth2PasswordRequestForm` as a dependency. It reads the
spec-required form fields (`username`, `password`, optional `scope`), so the endpoint
interoperates with the interactive docs "Authorize" button and standard OAuth2 clients. Return
`{"access_token": ..., "token_type": "bearer"}`, and on bad credentials raise `401` with the
`WWW-Authenticate: Bearer` header.

**Incorrect (custom JSON login, non-standard shape):**

```python
class Login(BaseModel):
    user: str
    pw: str


@router.post("/login")
async def login(body: Login):
    if not ok(body.user, body.pw):
        return {"error": "bad creds"}        # wrong shape, 200 on failure
    return {"token": make_token(body.user)}
```

**Correct (standard password flow):**

```python
from datetime import timedelta
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm


@router.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = authenticate(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": user.username}, expires_delta=timedelta(minutes=30)
    )
    return {"access_token": token, "token_type": "bearer"}
```

Pair with `security-password-hashing` (verify), `security-get-current-user` (decode), and a
signed-JWT `create_access_token` (`pip install pyjwt`).

See https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/
