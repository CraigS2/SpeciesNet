# Generated by Django 5.0.1 on 2024-02-02 13:34

import datetime
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0002_remove_species_lastupdated_species_global_region_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='species',
            options={'ordering': ['-created']},
        ),
        migrations.AlterModelOptions(
            name='speciesinstance',
            options={'ordering': ['-lastUpdated', '-created']},
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='approx_date_acquired',
            field=models.DateField(default=datetime.date.today, verbose_name='Date'),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='aquarist_notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='fry_rearing_notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='have_reared_fry',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='have_spawned',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='num_adults',
            field=models.PositiveSmallIntegerField(default=6),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='spawning_notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='speciesinstance',
            name='young_available',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='speciesinstance',
            name='genetic_traits',
            field=models.CharField(choices=[('AS', 'Aquarium Strain'), ('WC', 'Wild Caught'), ('F1', 'F1 First Generation'), ('F2', 'F2 Second Generation'), ('FX', 'FX 3rd or more Generation'), ('OT', 'Other')], default='AS', max_length=2),
        ),
        migrations.AlterField(
            model_name='speciesinstance',
            name='species',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='species_instances', to='species.species'),
        ),
        migrations.AlterField(
            model_name='speciesinstance',
            name='unique_traits',
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='speciesinstance',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='species_instances', to=settings.AUTH_USER_MODEL),
        ),
    ]
