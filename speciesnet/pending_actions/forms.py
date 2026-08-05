from django import forms


class BasePendingActionResponseForm(forms.Form):
    """Base form for pending-action response POSTs."""


class ConfirmPendingActionForm(BasePendingActionResponseForm):
    confirm = forms.BooleanField(initial=True, required=True, widget=forms.HiddenInput)
