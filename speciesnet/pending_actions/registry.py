from pending_actions.models import ActionType


_HANDLER_REGISTRY = {}


class ActionHandler:
    response_form_class = None

    def validate_payload(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Pending action payload must be a dictionary.')

    def build_email_context(self, action, token=None):
        raise NotImplementedError

    def get_response_form_class(self, action=None):
        """
        Resolve which response form applies to this specific action instance.
        Subclasses may override to make a per-instance decision (e.g. based on
        payload/related-object state) rather than a single fixed form per type.
        `action` is the PendingAction instance (may be None for generic lookups).
        """
        return self.response_form_class

    def requires_response(self, action):
        """
        Whether this specific action instance requires a user response before
        it can be considered resolved. Defaults to "does this action type have
        a response form at all" — subclasses may override to make a per-instance
        decision (e.g. based on payload contents) rather than a blanket per-type one.
        """
        return self.get_response_form_class(action) is not None

    def on_completed(self, action, response_data, request=None):
        return None


def register(slug):
    def decorator(handler_class):
        _HANDLER_REGISTRY[slug] = handler_class
        return handler_class
    return decorator


def get_handler_for_action_type(action_type):
    handler_class = _HANDLER_REGISTRY.get(action_type.slug)
    if handler_class is None:
        raise KeyError(f'No pending action handler registered for {action_type.slug}')
    return handler_class()


def get_handler_for_slug(slug):
    action_type = ActionType.objects.get(slug=slug)
    return get_handler_for_action_type(action_type)
