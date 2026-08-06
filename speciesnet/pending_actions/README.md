# Pending actions

This app replaces the older CARES-specific pattern of building and sending email directly inside views/services.

## Old CARES pattern

- `species/views/views_cares.py` decided when to notify
- `species/services/email_services.py` built and sent emails inline
- CARES-specific logic for recipients, token needs, and future response handling would have to grow in feature-specific code

## New pattern

1. Add or update an `ActionType` row (usually via migration or fixture data)
2. Implement an `ActionHandler` subclass for feature-specific payload validation, email context, and completion logic
3. Register the handler in `pending_actions/handlers.py`
4. If the action needs a user response, provide a response form and template-backed confirmation page
5. Create the action with `create_pending_action(...)` and let `send_action_email` deliver it asynchronously

## CARES as the reference example

- `cares_new_registration_notification` shows an FYI-only notification routed through the shared email pipeline without requiring a response
- `cares_status_change` shows a response-capable action with a signed single-use confirmation link rendered by the generic pending-actions view

## ⚠️ Important: Celery requires actively running worker and beat processes

Celery (and Redis as the broker) do **not** execute tasks automatically. A message sitting in the Redis queue will remain there indefinitely until an actively-running Celery worker process consumes and executes it. There is no implicit or default execution.

You need **two** separate processes running in addition to Redis:

- **`celery_worker`** — consumes tasks from the queue and executes them (sends emails, etc.). Without this, queued `send_action_email` tasks will never run.
- **`celery_beat`** — a scheduler that enqueues periodic tasks (like `sweep_expired_actions` and `sweep_old_task_results`) on their configured schedule. Without this, periodic tasks are never enqueued in the first place.

### Starting workers locally

```bash
# Worker — listens to the emails, celery, and default queues
celery -A speciesnet worker -l info -Q emails,celery,default

# Beat scheduler (separate terminal)
celery -A speciesnet beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Docker Compose

`docker-compose.yml` includes `celery_worker` and `celery_beat` services that reuse the same image as `django_gunicorn`. Starting the full stack (`docker compose up`) will bring all three up automatically.

### Bypassing the queue for manual testing (admin action)

If you need to send a pending-action email immediately without a running worker, use the Django admin:
**Pending Actions → select rows → "Run send_action_email now"**. This calls `.apply()` synchronously in-process, bypassing Redis entirely.

## Task result tracking vs. email archival

Two separate models serve different purposes:

| Model | Purpose | Retention |
|---|---|---|
| `django_celery_results.TaskResult` | Bounded Celery task activity log — useful for debugging failures, seeing task status | 30 days (swept by `sweep_old_task_results`; also purgeable via admin action) |
| `species.UserEmail` | **Permanent** durable archive of every email sent | **Never swept** — this is the authoritative record |

`sweep_old_task_results` only deletes `TaskResult` rows. It never touches `UserEmail`.

## Explicit non-goals in this implementation

- No cross-site sync Celery tasks yet
- No reminder emails yet
- No requester follow-up notifications on completion yet
