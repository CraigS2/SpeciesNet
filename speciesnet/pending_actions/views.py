import logging

from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import SetPasswordForm
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import FormView

from .models import PendingAction
from .registry import get_handler_for_action_type
from .tokens import PendingActionTokenExpired, PendingActionTokenInvalid, hash_token, load_signed_token

logger = logging.getLogger(__name__)

User = get_user_model()


class PendingActionConfirmView(FormView):
    template_name = 'pending_actions/confirm.html'
    success_url = reverse_lazy('pending_action_confirmation_complete')

    def dispatch(self, request, *args, **kwargs):
        self.token = kwargs.get('token')
        try:
            payload = load_signed_token(self.token, max_age=None)
        except PendingActionTokenExpired:
            return render(request, 'pending_actions/expired.html', status=410)
        except PendingActionTokenInvalid:
            raise Http404('Invalid action link.')

        self.action = get_object_or_404(PendingAction.objects.select_related('action_type', 'user'), pk=payload.get('action_id'))
        ttl_seconds = self.action.action_type.default_ttl_hours * 3600
        try:
            load_signed_token(self.token, max_age=ttl_seconds)
        except PendingActionTokenExpired:
            if self.action.status == PendingAction.Status.PENDING:
                self.action.status = PendingAction.Status.EXPIRED
                self.action.save(update_fields=['status'])
            return render(request, 'pending_actions/expired.html', {'action': self.action}, status=410)
        except PendingActionTokenInvalid:
            raise Http404('Invalid action link.')

        if self.action.token_hash != hash_token(self.token):
            raise Http404('Invalid action link.')
        if self.action.status == PendingAction.Status.COMPLETED:
            return render(request, 'pending_actions/already_used.html', {'action': self.action}, status=409)
        if self.action.status == PendingAction.Status.EXPIRED or self.action.expires_at <= timezone.now():
            if self.action.status == PendingAction.Status.PENDING:
                self.action.status = PendingAction.Status.EXPIRED
                self.action.save(update_fields=['status'])
            return render(request, 'pending_actions/expired.html', {'action': self.action}, status=410)
        if self.action.status != PendingAction.Status.PENDING:
            return render(request, 'pending_actions/already_used.html', {'action': self.action}, status=409)

        self.handler = get_handler_for_action_type(self.action.action_type)
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        form_class = self.handler.get_response_form_class(self.action)
        if form_class is None:
            raise Http404('This action does not accept responses.')
        return form_class

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Ensure uploaded files (e.g. an updated verification photo) reach the form.
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = self.action
        context['email_context'] = self.handler.build_email_context(self.action, token=self.token)
        return context

    def form_valid(self, form):
        self.action.status = PendingAction.Status.COMPLETED
        self.action.responded_at = timezone.now()
        self.action.response_data = {k: v for k, v in form.cleaned_data.items() if k != 'updated_photo'}
        self.action.save(update_fields=['status', 'responded_at', 'response_data'])
        self.handler.on_completed(self.action, form.cleaned_data, request=self.request)
        return render(self.request, 'pending_actions/completed.html', {'action': self.action})


def pending_action_confirmation_complete(request):
    return render(request, 'pending_actions/completed.html')

class ProxyActivationView(FormView):
    """
    Handles the proxy account activation flow.

    GET  — validate token, render set-password form.
    POST — set password, activate user, log them in, redirect to home.

    This is intentionally separate from PendingActionConfirmView because the
    activation flow needs to log the user in and redirect, not render a static
    'completed' page.  It uses the same token validation and PendingAction
    state machine; it simply takes over the final step.
    """

    template_name = 'pending_actions/proxy_activate.html'

    def _load_action(self, token):
        """Validate token and load the PendingAction, raising Http404 or rendering error on failure."""
        try:
            payload = load_signed_token(token, max_age=None)
        except PendingActionTokenExpired:
            return None, 'expired'
        except PendingActionTokenInvalid:
            return None, 'invalid'

        action = PendingAction.objects.select_related('action_type', 'user').filter(
            pk=payload.get('action_id'),
            action_type__slug='proxy_user_invite',
        ).first()
        if action is None:
            return None, 'invalid'

        if action.token_hash != hash_token(token):
            return None, 'invalid'

        ttl_seconds = action.action_type.default_ttl_hours * 3600
        try:
            load_signed_token(token, max_age=ttl_seconds)
        except PendingActionTokenExpired:
            if action.status == PendingAction.Status.PENDING:
                action.status = PendingAction.Status.EXPIRED
                action.save(update_fields=['status'])
            return action, 'expired'

        if action.status == PendingAction.Status.COMPLETED:
            return action, 'already_used'
        if action.status == PendingAction.Status.EXPIRED or action.expires_at <= timezone.now():
            if action.status == PendingAction.Status.PENDING:
                action.status = PendingAction.Status.EXPIRED
                action.save(update_fields=['status'])
            return action, 'expired'
        if action.status != PendingAction.Status.PENDING:
            return action, 'already_used'

        return action, 'ok'

    def dispatch(self, request, *args, **kwargs):
        self.token = kwargs.get('token')
        self.action, self.status = self._load_action(self.token)

        if self.status == 'invalid':
            raise Http404('Invalid activation link.')
        if self.status == 'expired':
            return render(request, 'pending_actions/expired.html', {'action': self.action}, status=410)
        if self.status == 'already_used':
            return render(request, 'pending_actions/already_used.html', {'action': self.action}, status=409)

        self.proxy_user = self.action.user
        if self.proxy_user is None or not self.proxy_user.is_proxy:
            raise Http404('Invalid activation link.')

        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return SetPasswordForm

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()
        return form_class(self.proxy_user, **self.get_form_kwargs())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = self.action
        context['club_name'] = self.action.payload.get('club_name', '')
        return context

    def form_valid(self, form):
        # Set the password and activate the account
        form.save()
        self.proxy_user.is_active = True
        self.proxy_user.save(update_fields=['is_active'])

        # Mark the PendingAction as completed
        self.action.status = PendingAction.Status.COMPLETED
        self.action.responded_at = timezone.now()
        self.action.save(update_fields=['status', 'responded_at'])

        # Log the user in directly via Django's ModelBackend (bypasses allauth)
        login(self.request, self.proxy_user, backend='django.contrib.auth.backends.ModelBackend')

        logger.info(
            'Proxy account activated: user_id=%s email=%s club_id=%s',
            self.proxy_user.pk,
            self.proxy_user.email,
            self.action.payload.get('club_id'),
        )
        return redirect('home')
