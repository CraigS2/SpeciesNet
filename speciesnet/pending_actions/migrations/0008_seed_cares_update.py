from django.db import migrations

# CARES Registration periodic update: 3 ActionTypes plus 3 django_celery_beat
# schedule rows, all seeded DISABLED. Turn a schedule on in Django admin
# (Periodic tasks -> tick Enabled); Beat uses DatabaseScheduler, so no deploy is needed.

ACTION_TYPES = [
    {
        'slug': 'cares_registration_update_individual',
        'display_name': 'CARES registration update request (aquarist)',
        'email_template': 'pending_actions/cares_update_individual_email.html',
        'default_ttl_hours': 720,
    },
    {
        'slug': 'cares_registration_update_liaison',
        'display_name': 'CARES registration update request (club liaison)',
        'email_template': 'pending_actions/cares_update_liaison_email.html',
        'default_ttl_hours': 720,
    },
    {
        'slug': 'cares_registration_closed_by_liaison',
        'display_name': 'CARES registrations closed by club liaison (notice)',
        'email_template': 'pending_actions/cares_closed_by_liaison_email.html',
        'default_ttl_hours': 72,
    },
]

# Individual campaign on the 1st of each quarter month, liaison follow-up 7 days later,
# expire/close nightly after the registration syncs (02:00 / 03:00 UTC).
PERIODIC_TASKS = [
    {
        'name': 'CARES update campaign: individuals (quarterly)',
        'task': 'pending_actions.tasks.run_cares_update_campaign',
        'kwargs': '{"kind": "individual"}',
        'crontab': {'minute': '0', 'hour': '9', 'day_of_month': '1', 'month_of_year': '1,4,7,10', 'day_of_week': '*'},
    },
    {
        'name': 'CARES update campaign: club liaisons (7 days after individuals)',
        'task': 'pending_actions.tasks.run_cares_update_campaign',
        'kwargs': '{"kind": "liaison", "min_age_days": 7}',
        'crontab': {'minute': '0', 'hour': '9', 'day_of_month': '8', 'month_of_year': '1,4,7,10', 'day_of_week': '*'},
    },
    {
        'name': 'CARES registrations: expire and close (nightly)',
        'task': 'pending_actions.tasks.expire_cares_registrations_task',
        'kwargs': '{}',
        'crontab': {'minute': '30', 'hour': '4', 'day_of_month': '*', 'month_of_year': '*', 'day_of_week': '*'},
    },
]


def seed_cares_update(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    for action_type in ACTION_TYPES:
        ActionType.objects.get_or_create(
            slug=action_type['slug'],
            defaults={
                'display_name': action_type['display_name'],
                'email_template': action_type['email_template'],
                'response_form_class': '',
                'default_ttl_hours': action_type['default_ttl_hours'],
                'is_active': True,
            },
        )

    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    for periodic in PERIODIC_TASKS:
        crontab, _ = CrontabSchedule.objects.get_or_create(timezone='UTC', **periodic['crontab'])
        PeriodicTask.objects.get_or_create(
            name=periodic['name'],
            defaults={
                'task': periodic['task'],
                'crontab': crontab,
                'kwargs': periodic['kwargs'],
                'enabled': False,
            },
        )


def remove_cares_update(apps, schema_editor):
    ActionType = apps.get_model('pending_actions', 'ActionType')
    ActionType.objects.filter(slug__in=[a['slug'] for a in ACTION_TYPES]).delete()
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name__in=[p['name'] for p in PERIODIC_TASKS]).delete()


class Migration(migrations.Migration):
    # Depends on both existing leaves (0006 and 0007 branch from different 0002s).
    dependencies = [
        ('pending_actions', '0006_seed_bap_notes_required_action_type'),
        ('pending_actions', '0007_seed_cares_registration_summary_action_type'),
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]

    operations = [
        migrations.RunPython(seed_cares_update, remove_cares_update),
    ]
