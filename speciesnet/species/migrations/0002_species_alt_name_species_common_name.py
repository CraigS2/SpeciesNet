# Generated by Django 5.0.6 on 2024-06-21 10:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='species',
            name='alt_name',
            field=models.CharField(blank=True, max_length=240, null=True),
        ),
        migrations.AddField(
            model_name='species',
            name='common_name',
            field=models.CharField(blank=True, max_length=240, null=True),
        ),
    ]