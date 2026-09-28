from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ActionType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('display_name', models.CharField(max_length=255)),
                ('email_template', models.CharField(max_length=255)),
                ('response_form_class', models.CharField(blank=True, max_length=255)),
                ('default_ttl_hours', models.PositiveSmallIntegerField(default=72)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['slug']},
        ),
        migrations.CreateModel(
            name='PendingAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled')], db_index=True, default='PENDING', max_length=20)),
                ('token_hash', models.CharField(db_index=True, max_length=64, unique=True)),
                ('payload', models.JSONField(default=dict)),
                ('payload_schema_version', models.PositiveSmallIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('response_data', models.JSONField(blank=True, null=True)),
                ('action_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pending_actions', to='pending_actions.actiontype')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pending_actions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='pendingaction',
            index=models.Index(fields=['status', 'expires_at'], name='pending_act_status_e1d79f_idx'),
        ),
    ]
