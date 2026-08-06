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

## Explicit non-goals in this implementation

- No cross-site sync Celery tasks yet
- No reminder emails yet
- No requester follow-up notifications on completion yet
