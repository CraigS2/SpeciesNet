from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, strip_tags

from species.asn_tools.asn_img_tools import processUploadedImageFile
from species.models import CaresRegistration, UserEmail

from .forms import CaresClarificationResponseForm, ConfirmPendingActionForm
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

    def _get_registration(self, action):
        return CaresRegistration.objects.filter(pk=action.payload.get('registration_id')).first()

    def _is_pending_clarification(self, action):
        registration = self._get_registration(action)
        return registration is not None and registration.status == CaresRegistration.CaresRegistrationStatus.PENDING

    def get_response_form_class(self, action=None):
        if action is not None and self._is_pending_clarification(action):
            return CaresClarificationResponseForm
        return self.response_form_class

    def requires_response(self, action):
        """
        cares_status_change is shared by every registration status transition
        (approved, declined, pending-clarification, etc.) but only the PENDING
        status genuinely requires the aquarist to respond/clarify. All other
        status-change notifications are informational and should be considered
        complete once the email is sent — leaving them PENDING forever is misleading.
        """
        registration = self._get_registration(action)
        if registration is None:
            # Registration missing/deleted — nothing meaningful to wait on.
            return False
        return registration.status == CaresRegistration.CaresRegistrationStatus.PENDING

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

    def on_completed(self, action, response_data, request=None):
        """
        Handles both response form variants:
        - ConfirmPendingActionForm: simple acknowledgement, nothing further to persist.
        - CaresClarificationResponseForm: aquarist may have supplied response_text
          and/or an updated_photo. response_text (plus a 'Species photo updated' note
          when a photo was supplied) is appended to species_source (avoiding a schema
          migration for a dedicated field). updated_photo replaces verification_photo
          and is run through processUploadedImageFile for consistent resizing, exactly
          like every other verification-photo upload path in this codebase. The
          registration is moved from PENDING back to RESUBMIT so it re-enters the
          approver's queue.
        """
        registration = self._get_registration(action)
        if registration is None:
            return None

        response_text = (response_data.get('response_text') or '').strip()
        updated_photo = response_data.get('updated_photo')

        note_parts = []
        if response_text:
            note_parts.append(response_text)
        if updated_photo:
            note_parts.append('Species photo updated')

        if note_parts:
            today = timezone.now().strftime('%Y-%m-%d')
            appended = f"Updated {today}:\n" + '\n'.join(note_parts)
            registration.species_source = f'{registration.species_source}\n\n{appended}'.strip()

        if updated_photo:
            registration.verification_photo = updated_photo

        if registration.status == CaresRegistration.CaresRegistrationStatus.PENDING:
            registration.status = CaresRegistration.CaresRegistrationStatus.RESUBMIT

        registration.save()

        # processUploadedImageFile opens image_field.path, so it must run after the
        # file above has already been written to disk via registration.save().
        if updated_photo:
            processUploadedImageFile(registration.verification_photo, registration.name, request)
            registration.save(update_fields=['verification_photo'])

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


@register('proxy_user_invite')
class ProxyUserInviteHandler(ActionHandler):
    """
    Handles the proxy_user_invite action type.

    The invite email contains a single-use activation link.  The recipient
    lands on ProxyActivationView (not PendingActionConfirmView) which handles
    password-setting and account activation directly.  This handler's only
    responsibility is building the email context; there is no response form
    and on_completed is never called through the confirm view for this type.
    """

    def validate_payload(self, payload):
        super().validate_payload(payload)
        required = {'to_email', 'club_id', 'club_name', 'user_id', 'base_url'}
        missing = required.difference(payload.keys())
        if missing:
            raise ValueError(f'Missing required proxy invite payload values: {sorted(missing)}')

    def requires_response(self, action):
        return False

    def build_email_context(self, action, token=None):
        token = token or action.payload.get('token')
        base_url = action.payload.get('base_url', '').rstrip('/')
        # Activation URL handled by pending_actions.views.ProxyActivationView
        activation_path = reverse('proxy_activate', args=[token]) if token else ''
        activation_url = f'{base_url}{activation_path}' if base_url else activation_path
        club_name = action.payload.get('club_name', '')
        invited_by = action.payload.get('invited_by_username', '')
        return {
            'action': action,
            'to_email': action.payload['to_email'],
            'club_name': club_name,
            'invited_by_username': invited_by,
            'activation_url': activation_url,
            'subject': f'You have been invited to join {club_name} on AquaristSpecies',
            'archive_name': f'Proxy invite to {action.payload["to_email"]} for {club_name}',
            'archive_text': (
                f"Invited: {action.payload['to_email']}\n"
                f"Club: {club_name}\n"
                f"Invited by: {invited_by}\n"
                f"Activation URL: {activation_url}"
            ),
        }
