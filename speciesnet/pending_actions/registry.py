from pending_actions.models import ActionType


_HANDLER_REGISTRY = {}


class ActionHandler:
    response_form_class = None

    def validate_payload(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Pending action payload must be a dictionary.')

    def build_email_context(self, action, token=None):
        raise NotImplementedError

    def get_response_form_class(self, action_type=None):
        if action_type and action_type.response_form_class:
            return action_type.get_response_form_class()
        return self.response_form_class

    def on_completed(self, action, response_data):
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
