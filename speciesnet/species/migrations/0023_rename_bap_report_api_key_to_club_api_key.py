import species.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0022_aquaristclub_bap_report_api_key'),
    ]

    operations = [
        migrations.RenameField(
            model_name='aquaristclub',
            old_name='bap_report_api_key',
            new_name='club_api_key',
        ),
        migrations.RenameField(
            model_name='aquaristclub',
            old_name='bap_report_api_key_hint',
            new_name='club_api_key_hint',
        ),
        migrations.AlterField(
            model_name='aquaristclub',
            name='club_api_key',
            field=species.models.EncryptedTextField(blank=True, help_text='Club admin API key for club-scoped API access (encrypted at rest; never redisplayed after save)'),
        ),
        migrations.AlterField(
            model_name='aquaristclub',
            name='club_api_key_hint',
            field=models.CharField(blank=True, help_text="Redacted fingerprint of the club admin API key, e.g. 'club_539d••••1010'", max_length=30),
        ),
    ]
