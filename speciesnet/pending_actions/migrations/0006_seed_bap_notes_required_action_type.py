from django.db import migrations


def seed_bap_notes_required(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.get_or_create(
        slug='bap_notes_required',
        defaults={
            'display_name': 'BAP/SMP required notes request',
            'email_template': 'pending_actions/bap_notes_required_email.html',
            'response_form_class': 'pending_actions.forms.BapNotesRequiredForm',
            'default_ttl_hours': 168,
            'is_active': True,
        },
    )


def remove_bap_notes_required(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.filter(slug='bap_notes_required').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pending_actions', '0005_seed_bap_join_invite_action_type'),
    ]

    operations = [
        migrations.RunPython(seed_bap_notes_required, remove_bap_notes_required),
    ]
