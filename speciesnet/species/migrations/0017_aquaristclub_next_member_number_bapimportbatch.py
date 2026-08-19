# Generated migration for next_member_number and BapImportBatch

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0016_remove_caresregistration_species_caresreg_external_id_positive_uniq_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='aquaristclub',
            name='next_member_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name='BapImportBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('auction_name', models.CharField(max_length=240)),
                ('auction_date', models.DateField(blank=True, null=True)),
                ('working_csv_file', models.FileField(blank=True, null=True, upload_to='bap_imports/working/')),
                ('status', models.CharField(
                    choices=[('REVIEW', 'In Review'), ('PROCESSED', 'Processed')],
                    default='REVIEW',
                    max_length=12,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('club', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='bap_import_batches',
                    to='species.aquaristclub',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='bap_import_batches_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('processed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='bap_import_batches_processed',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'BAP Import Batch',
                'verbose_name_plural': 'BAP Import Batches',
                'ordering': ['-created_at'],
            },
        ),
    ]
