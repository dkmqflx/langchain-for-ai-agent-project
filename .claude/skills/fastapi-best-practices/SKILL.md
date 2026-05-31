---
name: fastapi-best-practices
description: Use when writing, reviewing, or refactoring FastAPI code — endpoints, APIRouter, query/path parameters, dependencies (Depends), Pydantic request/response models, error handling, async def vs def, lifespan events, security/auth, password hashing, streaming, background tasks, settings, testing, middleware, or CORS. Triggers on FastAPI backend work, route design, or API code review.
license: MIT
metadata:
  author: dkmqflx
  version: "2.0.0"
---

# FastAPI Best Practices

Reference guide for writing FastAPI code that follows the official documentation
(https://fastapi.tiangolo.com/). 41 rules across 13 categories, prioritized by impact —
security and correctness first, structure/validation/testing next, performance and polish
last. Each rule pairs an incorrect example with the official correct pattern and links the
relevant docs page.

## When to Apply

Reference these guidelines when:
- Writing new FastAPI endpoints, routers, parameters, or Pydantic models
- Designing dependency injection, authentication, password storage, or error handling
- Adding streaming, background tasks, settings/config, or middleware
- Writing tests for a FastAPI app
- Reviewing or refactoring a FastAPI backend

## Rule Categories by Priority

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Request/Response Models | CRITICAL | `model-` |
| 2 | Security & Authentication | CRITICAL | `security-` |
| 3 | Request Parameters & Validation | HIGH | `params-` |
| 4 | App Structure & Routing | HIGH | `structure-` |
| 5 | Dependency Injection | HIGH | `di-` |
| 6 | Error Handling | HIGH | `error-` |
| 7 | Testing | HIGH | `testing-` |
| 8 | Async & Concurrency | MEDIUM | `async-` |
| 9 | Responses & Streaming | MEDIUM | `response-` |
| 10 | Background Tasks & Config | MEDIUM | `background-`, `config-` |
| 11 | Lifespan & Resources | MEDIUM | `lifespan-` |
| 12 | Middleware & Cross-cutting | MEDIUM | `mw-` |
| 13 | OpenAPI Documentation | LOW | `docs-` |

## Quick Reference

### 1. Request/Response Models (CRITICAL)

- `model-response-model` — declare a response model on every endpoint
- `model-separate-input-output` — separate input vs output models so secrets never leak
- `model-return-type-annotation` — prefer the return-type annotation; use `response_model=` only when types differ
- `model-pydantic-validation` — validate with Pydantic `Field`/`Literal`, not manual `if` checks
- `model-exclude-unset` — `response_model_exclude_unset` for partial/sparse data

### 2. Security & Authentication (CRITICAL)

- `security-oauth2-bearer` — extract Bearer tokens with `OAuth2PasswordBearer` + `Annotated`
- `security-get-current-user` — resolve the current user in a `get_current_user` dependency
- `security-router-auth` — protect route groups via `APIRouter(dependencies=[...])`
- `security-password-hashing` — hash passwords (pwdlib/passlib); never store plaintext
- `security-token-endpoint` — build the token route with `OAuth2PasswordRequestForm`

### 3. Request Parameters & Validation (HIGH)

- `params-query-validation` — validate query params with `Annotated[..., Query()]`
- `params-path-validation` — constrain path params with `Annotated[..., Path()]` (`ge`/`le`)
- `params-query-param-models` — group filter/sort/search params in a Pydantic query model
- `params-pagination` — paginate lists with bounded `limit`/`offset`; empty list, not 404

### 4. App Structure & Routing (HIGH)

- `structure-apirouter-prefix-tags` — give each `APIRouter` a `prefix` and `tags`
- `structure-bigger-app-layout` — split into `routers/`, `models/`, `dependencies.py`
- `structure-import-submodule` — import the submodule, not the `router` variable
- `structure-status-code-decorator` — set the success `status_code` in the decorator (201 for creation)

### 5. Dependency Injection (HIGH)

- `di-use-depends` — share logic via `Depends()`, not manual instantiation
- `di-annotated` — use `Annotated[T, Depends(...)]` over the legacy default-value form
- `di-reusable-type-alias` — hoist repeated dependencies into a type alias
- `di-yield-cleanup` — use `yield` dependencies for setup/teardown (DB sessions, files)

### 6. Error Handling (HIGH)

- `error-raise-httpexception` — `raise HTTPException`, never `return` an error
- `error-specific-status-codes` — use specific codes (404/400/409), not a blanket 500
- `error-reraise-httpexception` — re-raise `HTTPException` in broad `except` blocks
- `error-custom-handler` — centralize cross-cutting errors in `@app.exception_handler`

### 7. Testing (HIGH)

- `testing-testclient` — test endpoints through `TestClient` (real HTTP, in-process)
- `testing-dependency-overrides` — swap deps with `app.dependency_overrides`, not monkeypatch
- `testing-async-client` — use httpx `AsyncClient` + `ASGITransport` for async tests

### 8. Async & Concurrency (MEDIUM)

- `async-def-vs-def` — choose `async def` vs `def` by the library you call
- `async-no-blocking-in-async` — never call blocking code inside `async def`
- `async-await-all-io` — `await` every async call

### 9. Responses & Streaming (MEDIUM)

- `response-streaming` — stream long/LLM responses with `StreamingResponse`, not buffering
- `response-additional-responses` — document non-200 responses in OpenAPI

### 10. Background Tasks & Config (MEDIUM)

- `background-tasks` — use `BackgroundTasks` for post-response work
- `config-pydantic-settings` — read config from env with `pydantic-settings` + `@lru_cache`

### 11. Lifespan & Resources (MEDIUM)

- `lifespan-context-manager` — use the `lifespan` context manager, not deprecated `@app.on_event`
- `lifespan-load-once` — load expensive resources (models, indexes) once at startup

### 12. Middleware & Cross-cutting (MEDIUM)

- `mw-cors` — configure `CORSMiddleware` with an explicit origin allowlist
- `mw-custom-http` — add timing/request-id/logging via `@app.middleware("http")`

### 13. OpenAPI Documentation (LOW)

- `docs-openapi-metadata` — add `summary`, `description`, `tags`, `response_description`

## How to Use

Read the individual rule file for the detailed explanation and before/after example:

```
rules/model-separate-input-output.md
rules/params-query-param-models.md
rules/security-password-hashing.md
rules/testing-dependency-overrides.md
```

Each rule file contains:
- A short explanation of why it matters, tied to the official docs
- An **Incorrect** example (the antipattern)
- A **Correct** example (the official pattern)
- A link to the relevant page on https://fastapi.tiangolo.com/

All examples follow the official FastAPI documentation and avoid deprecated APIs.
