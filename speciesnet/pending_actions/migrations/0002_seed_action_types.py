from django.db import migrations


def seed_action_types(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.update_or_create(
        slug='cares_status_change',
        defaults={
            'display_name': 'CARES status change notification',
            'email_template': 'pending_actions/cares_status_change_email.html',
            'response_form_class': 'pending_actions.forms.ConfirmPendingActionForm',
            'default_ttl_hours': 72,
            'is_active': True,
        },
    )
    ActionType.objects.update_or_create(
        slug='cares_new_registration_notification',
        defaults={
            'display_name': 'CARES new registration notification',
            'email_template': 'species/cares/email_new_registration.html',
            'response_form_class': '',
            'default_ttl_hours': 72,
            'is_active': True,
        },
    )


def unseed_action_types(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.filter(slug__in=['cares_status_change', 'cares_new_registration_notification']).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pending_actions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_action_types, unseed_action_types),
    ]
