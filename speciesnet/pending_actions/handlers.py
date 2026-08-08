from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape, strip_tags

from species.models import CaresRegistration

from .forms import ConfirmPendingActionForm
from .registry import ActionHandler, register


@register('cares_status_change')
class CaresStatusChangeHandler(ActionHandler):
    response_form_class = ConfirmPendingActionForm

    def validate_payload(self, payload):
        super().validate_payload(payload)
        required = {'registration_id', 'subject', 'body', 'to_email', 'aquarist_name'}
        missing = required.difference(payload.keys())
        if missing:
            raise ValueError(f'Missing required CARES status payload values: {sorted(missing)}')

    def build_email_context(self, action, token=None):
        registration = CaresRegistration.objects.select_related('species').get(pk=action.payload['registration_id'])
        token = token or action.payload.get('token')
        confirm_path = reverse('pending_action_confirm', args=[token]) if token else ''
        site_url = action.payload.get('site_url', '').rstrip('/')
        confirm_url = f'{site_url}{confirm_path}' if site_url else confirm_path
        body = action.payload['body']
        escaped_body = escape(body).replace('\n', '<br>')
        species_name = registration.species.name if registration.species else registration.name
        archive_body = f"To: {action.payload['aquarist_name']}\n Email: {action.payload['to_email']}\n\n{body}"
        return {
            'action': action,
            'registration': registration,
            'species_name': species_name,
            'subject': action.payload['subject'],
            'body': body,
            'escaped_body': escaped_body,
            'to_email': action.payload['to_email'],
            'aquarist_name': action.payload['aquarist_name'],
            'reply_to': action.payload.get('reply_to'),
            'confirm_url': confirm_url,
            'archive_name': f"CARES status update to {action.payload['aquarist_name']}",
            'archive_text': archive_body,
        }

    def on_completed(self, action, response_data):
        return None


@register('cares_new_registration_notification')
class CaresNewRegistrationNotificationHandler(ActionHandler):
    def validate_payload(self, payload):
        super().validate_payload(payload)
        required = {'registration_id', 'to_email', 'approver_name'}
        missing = required.difference(payload.keys())
        if missing:
            raise ValueError(f'Missing required CARES notification payload values: {sorted(missing)}')

    def build_email_context(self, action, token=None):
        registration = CaresRegistration.objects.select_related('species').get(pk=action.payload['registration_id'])
        photo_url = None
        if registration.verification_photo:
            site_url = action.payload.get('site2_url', '').rstrip('/')
            if site_url:
                photo_url = f'{site_url}{registration.verification_photo.url}'
        html_body = render_to_string(
            'species/cares/email_new_registration.html',
            {
                'registration': registration,
                'species': registration.species,
                'photo_url': photo_url,
            },
        )
        plain_body = strip_tags(html_body)
        return {
            'registration': registration,
            'species': registration.species,
            'photo_url': photo_url,
            'subject': f'New CARES Registration: {registration.species.name}',
            'to_email': action.payload['to_email'],
            'approver_name': action.payload['approver_name'],
            'archive_name': f"CARES registration notification to {action.payload['username']}",
            'archive_text': f"To: {action.payload['approver_name']}\nEmail: {action.payload['to_email']}\n{plain_body}",
            'send_to_user': action.user,
        }
