"""
PASS1_SCOPE.md section 3.5: make Species.name unique.

Deploy this LAST, after both databases have been cleaned up with
`manage.py normalize_species_text --apply` (CSO first, then ASN) and any
collisions reported by that command have been merged by hand. Applying it
before that will fail with a DB-level IntegrityError on existing
duplicate/case-only-duplicate names.

MariaDB's default collation is case-insensitive, so this constraint also
rejects case-only duplicates (e.g. "Kenya gold" vs "kenya gold") without
any extra configuration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0015_bap_cares_smp_auction_lot_import_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='species',
            name='name',
            field=models.CharField(max_length=240, unique=True),
        ),
    ]
