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
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
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


class BapNotesRequiredForm(BasePendingActionResponseForm):
    spawning_notes = forms.CharField(
        label='Spawning notes',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    fry_rearing_notes = forms.CharField(
        label='Fry-rearing notes',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    def __init__(self, *args, missing_fields=None, **kwargs):
        super().__init__(*args, **kwargs)
        missing_fields = set(missing_fields or [])
        if 'spawning_notes' not in missing_fields:
            self.fields.pop('spawning_notes', None)
        if 'fry_rearing_notes' not in missing_fields:
            self.fields.pop('fry_rearing_notes', None)

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.fields.keys():
            value = (cleaned_data.get(field_name) or '').strip()
            if not value:
                self.add_error(field_name, 'This field is required.')
            cleaned_data[field_name] = value
        return cleaned_data