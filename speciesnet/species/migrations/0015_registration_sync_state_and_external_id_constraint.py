# Generated migration for RegistrationSyncState model
# and partial unique constraint on CaresRegistration.external_id > 0.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0014_species_manage_collection_locations_and_more'),
    ]

    operations = [
        # 1. New RegistrationSyncState model for tracking last-sync timestamps.
        migrations.CreateModel(
            name='RegistrationSyncState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', models.CharField(
                    choices=[
                        ('site1_to_site2', 'Site1 \u2192 Site2 (new registrations)'),
                        ('site2_to_site1', 'Site2 \u2192 Site1 (status updates)'),
                    ],
                    max_length=20,
                    unique=True,
                )),
                ('last_synced_at', models.DateTimeField(
                    blank=True,
                    null=True,
                    help_text='Timestamp of the last successful sync run for this direction.',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Registration Sync State',
                'verbose_name_plural': 'Registration Sync States',
            },
        ),

        # 2. Partial unique index on CaresRegistration.external_id when external_id > 0.
        #    This is a database-level guard so neither the CSV nor API path can create
        #    duplicate registrations for the same Site1 source record.
        migrations.AddConstraint(
            model_name='caresregistration',
            constraint=models.UniqueConstraint(
                fields=['external_id'],
                condition=models.Q(external_id__gt=0),
                name='species_caresreg_external_id_positive_uniq',
            ),
        ),
    ]
