---
title: Use BackgroundTasks for Post-Response Work
impact: MEDIUM
impactDescription: the client gets its response immediately; side work runs after
tags: fastapi, backgroundtasks, async, email, notification, celery, post-response
---

## Use BackgroundTasks for Post-Response Work

When work doesn't need to finish before the client gets its answer — sending an email,
writing an audit log, warming a cache — declare a `BackgroundTasks` parameter and schedule it
with `add_task`. FastAPI returns the response first, then runs the task. Don't `await` such
side work inline; it just delays the response.

**Incorrect (client waits for the email to send):**

```python
@router.post("/signup")
async def signup(user: UserIn):
    created = create_user(user)
    await send_welcome_email(created.email)   # client blocked on SMTP
    return created
```

**Correct (respond now, send email after):**

```python
from fastapi import BackgroundTasks


@router.post("/signup")
async def signup(user: UserIn, background_tasks: BackgroundTasks):
    created = create_user(user)
    background_tasks.add_task(send_welcome_email, created.email)
    return created
```

`add_task` takes the function plus its args/kwargs; the function may be `async def` or `def`.
For heavy or cross-process jobs (long compute, retries, multiple workers), reach for a real
queue like Celery instead.

See https://fastapi.tiangolo.com/tutorial/background-tasks/
