# Migration: Part A - Add auction.fish fields to AquaristClub
#            Part B - Rename auction_name/auction_date on BapImportBatch

from django.db import migrations, models
import species.models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0019_backfill_bap_year_and_lifetime_totals'),
    ]

    operations = [
        # Part A: auction.fish integration fields on AquaristClub
        migrations.AddField(
            model_name='aquaristclub',
            name='auction_fish_slug',
            field=models.CharField(
                blank=True,
                help_text="Club slug on auction.fish, e.g. 'pioneer-valley-aquarium-society'",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='aquaristclub',
            name='auction_fish_api_key',
            field=species.models.EncryptedTextField(
                blank=True,
                help_text='API key for auction.fish (encrypted at rest; never redisplayed after save)',
            ),
        ),
        migrations.AddField(
            model_name='aquaristclub',
            name='auction_fish_api_key_hint',
            field=models.CharField(
                blank=True,
                help_text="Redacted fingerprint of the stored API key, e.g. 'ck_539d\u2022\u2022\u2022\u20221010'",
                max_length=30,
            ),
        ),
        # Part B: rename BapImportBatch fields
        migrations.RenameField(
            model_name='bapimportbatch',
            old_name='auction_name',
            new_name='club_or_auction_name',
        ),
        migrations.RenameField(
            model_name='bapimportbatch',
            old_name='auction_date',
            new_name='auction_pull_date',
        ),
    ]
