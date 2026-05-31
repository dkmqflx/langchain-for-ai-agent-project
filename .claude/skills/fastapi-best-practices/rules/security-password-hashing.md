---
title: Hash Passwords — Never Store Plaintext
impact: CRITICAL
impactDescription: a DB leak doesn't expose user passwords; resists timing attacks
tags: fastapi, security, password, hashing, pwdlib, passlib, argon2, bcrypt
---

## Hash Passwords — Never Store Plaintext

Store a one-way hash of each password, never the password itself, and never an
encrypted/recoverable form. Hash on signup, verify on login by hashing the attempt and
comparing. The current FastAPI docs use `pwdlib` (Argon2); `passlib` (bcrypt) is the
established alternative. Also verify against a dummy hash when the user doesn't exist, so login
timing doesn't reveal which usernames are valid.

**Incorrect (plaintext or reversible storage):**

```python
def create_user(username: str, password: str):
    db.save(username=username, password=password)   # plaintext in the DB — never do this


def login(username: str, password: str):
    user = db.get(username)
    return user.password == password                # compares plaintext
```

**Correct (hash on write, verify on read):**

```python
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy")


def create_user(username: str, password: str):
    db.save(username=username, hashed_password=password_hash.hash(password))


def authenticate(username: str, password: str) -> User | None:
    user = db.get(username)
    if user is None:
        password_hash.verify(password, DUMMY_HASH)   # constant-time-ish; avoid user enumeration
        return None
    if not password_hash.verify(password, user.hashed_password):
        return None
    return user
```

`pwdlib` is a separate install: `pip install "pwdlib[argon2]"`.

See https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
