# Generated migration for BAP report API key fields on AquaristClub

from django.db import migrations, models
import species.models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0021_aquaristclub_cares_liaison_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='aquaristclub',
            name='bap_report_api_key',
            field=species.models.EncryptedTextField(blank=True, help_text="BAP report API key for club-scoped species-instance sync (encrypted at rest; never redisplayed after save)"),
        ),
        migrations.AddField(
            model_name='aquaristclub',
            name='bap_report_api_key_hint',
            field=models.CharField(blank=True, help_text="Redacted fingerprint of the BAP report API key, e.g. 'bap_539d••••1010'", max_length=30),
        ),
    ]
