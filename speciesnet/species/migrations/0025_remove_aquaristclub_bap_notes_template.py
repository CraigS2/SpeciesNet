# Hard delete: bap_notes_template is obsolete, no production data worth preserving.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0024_aquaristclubemailalias'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='aquaristclub',
            name='bap_notes_template',
        ),
    ]
