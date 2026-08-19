"""Seed the bap_join_invite ActionType."""

from django.db import migrations


def seed_bap_join_invite(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.get_or_create(
        slug='bap_join_invite',
        defaults={
            'display_name': 'BAP club join invitation',
            'email_template': 'pending_actions/bap_join_invite_email.html',
            'response_form_class': '',
            'default_ttl_hours': 168,
            'is_active': True,
        },
    )


def remove_bap_join_invite(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.filter(slug='bap_join_invite').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pending_actions', '0004_seed_proxy_invite_action_type'),
    ]

    operations = [
        migrations.RunPython(seed_bap_join_invite, remove_bap_join_invite),
    ]
