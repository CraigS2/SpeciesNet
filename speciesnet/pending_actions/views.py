from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import FormView

from .models import PendingAction
from .registry import get_handler_for_action_type
from .tokens import PendingActionTokenExpired, PendingActionTokenInvalid, hash_token, load_signed_token


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
        form_class = self.handler.get_response_form_class(self.action.action_type)
        if form_class is None:
            raise Http404('This action does not accept responses.')
        return form_class

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = self.action
        context['email_context'] = self.handler.build_email_context(self.action, token=self.token)
        return context

    def form_valid(self, form):
        self.action.status = PendingAction.Status.COMPLETED
        self.action.responded_at = timezone.now()
        self.action.response_data = form.cleaned_data
        self.action.save(update_fields=['status', 'responded_at', 'response_data'])
        self.handler.on_completed(self.action, form.cleaned_data)
        return render(self.request, 'pending_actions/completed.html', {'action': self.action})


def pending_action_confirmation_complete(request):
    return render(request, 'pending_actions/completed.html')
