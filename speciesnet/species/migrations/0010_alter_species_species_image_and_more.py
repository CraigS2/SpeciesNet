# Generated by Django 5.0.1 on 2024-03-26 11:18

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0009_species_category'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='species',
            name='species_image',
            field=models.ImageField(blank=True, null=True, upload_to='images/%Y/%m/%d'),
        ),
        migrations.AlterField(
            model_name='speciesinstance',
            name='instance_image',
            field=models.ImageField(blank=True, null=True, upload_to='images/%Y/%m/%d'),
        ),
        migrations.AlterField(
            model_name='speciesinstance',
            name='species',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='species_instances', to='species.species'),
        ),
        migrations.CreateModel(
            name='ImportArchive',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('import_csv_file', models.FileField(upload_to='uploads/%Y/%m/%d/')),
                ('import_results_file', models.FileField(blank=True, null=True, upload_to='uploads/%Y/%m/%d/')),
                ('import_status', models.CharField(choices=[('PEND', 'Pending'), ('IWER', 'Imported with Errors'), ('ICLN', 'Imported without Errors'), ('FAIL', 'F2 Second Generation')], default='PEND', max_length=4)),
                ('dateImported', models.DateTimeField(auto_now_add=True)),
                ('aquarist', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='aquarist_imports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-dateImported'],
            },
        ),
    ]
