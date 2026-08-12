from django import forms


class BasePendingActionResponseForm(forms.Form):
    """Base form for pending-action response POSTs."""


class ConfirmPendingActionForm(BasePendingActionResponseForm):
    confirm = forms.BooleanField(initial=True, required=True, widget=forms.HiddenInput)


class CaresClarificationResponseForm(BasePendingActionResponseForm):
    """
    Response form for a cares_status_change action where the registration status
    is PENDING — i.e. the approver needs clarification and/or a better verification
    photo from the aquarist before the registration can move forward.
    """
    response_text = forms.CharField(
        label='Additional information',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    updated_photo = forms.ImageField(
        label='Updated verification photo',
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()
        response_text = (cleaned_data.get('response_text') or '').strip()
        updated_photo = cleaned_data.get('updated_photo')
        if not response_text and not updated_photo:
            raise forms.ValidationError(
                'Please provide additional information and/or an updated verification photo.'
            )
        cleaned_data['response_text'] = response_text
        return cleaned_data