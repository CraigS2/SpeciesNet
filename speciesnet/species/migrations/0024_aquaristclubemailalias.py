# Generated for AquaristClubEmailAlias (BAP import: per-club email alias resolution)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('species', '0015_cares_reg_synch_state_bap_improvements_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AquaristClubEmailAlias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_email', models.EmailField(max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('club', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_aliases', to='species.aquaristclub')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='club_email_aliases', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Club Email Alias',
                'verbose_name_plural': 'Club Email Aliases',
                'ordering': ['club', 'alias_email'],
            },
        ),
        migrations.AddConstraint(
            model_name='aquaristclubemailalias',
            constraint=models.UniqueConstraint(fields=('club', 'alias_email'), name='uniq_club_alias_email'),
        ),
    ]
