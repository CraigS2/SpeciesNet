# Generated migration

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0012_remove_species_image_photo_credit_from_staging'),
    ]

    operations = [
        migrations.AlterField(
            model_name='speciesimportstaging',
            name='review_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending review'),
                    ('APPROVED', 'Approved'),
                    ('OVERRIDE', 'Approved with Override'),
                    ('REJECTED', 'Rejected'),
                ],
                default='PENDING',
                max_length=10,
            ),
        ),
    ]
