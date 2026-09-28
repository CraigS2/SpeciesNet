from django.db import migrations


def seed_proxy_invite(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.update_or_create(
        slug='proxy_user_invite',
        defaults={
            'display_name': 'Proxy user account invitation',
            'email_template': 'pending_actions/proxy_invite_email.html',
            'response_form_class': '',
            'default_ttl_hours': 168,   # 7 days — reasonable window for a human to act on an invite
            'is_active': True,
        },
    )


def unseed_proxy_invite(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.filter(slug='proxy_user_invite').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pending_actions', '0003_rename_pending_action_status_idx'),
    ]

    operations = [
        migrations.RunPython(seed_proxy_invite, unseed_proxy_invite),
    ]
