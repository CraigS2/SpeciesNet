from django.db import migrations


def seed_cares_registration_summary(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.get_or_create(
        slug='cares_registration_summary',
        defaults={
            'display_name': 'CARES registration status summary',
            'email_template': 'species/cares/email_registration_summary.html',
            'response_form_class': '',
            'default_ttl_hours': 24,
            'is_active': True,
        },
    )


def remove_cares_registration_summary(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.filter(slug='cares_registration_summary').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pending_actions', '0002_seed_species_action_types'),
    ]

    operations = [
        migrations.RunPython(seed_cares_registration_summary, remove_cares_registration_summary),
    ]
