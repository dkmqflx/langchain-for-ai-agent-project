---
title: Configure CORS With an Explicit Origin Allowlist
impact: MEDIUM
impactDescription: browsers can call the API from trusted origins without opening it to all
tags: fastapi, cors, corsmiddleware, middleware, origins, browser, security
---

## Configure CORS With an Explicit Origin Allowlist

A browser frontend on a different origin needs `CORSMiddleware`. List the exact origins you
trust rather than reflexively allowing everything. Note that `allow_origins=["*"]` cannot be
combined with `allow_credentials=True` — that pairing is rejected by browsers, so an explicit
allowlist is required when you send cookies/credentials.

**Risky (wildcard origins with credentials — broken and over-permissive):**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,   # incompatible with "*"
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Correct (explicit allowlist):**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://app.example.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`backend/main.py` configures CORS with an explicit origin list for the Next.js frontend.

See https://fastapi.tiangolo.com/tutorial/cors/
