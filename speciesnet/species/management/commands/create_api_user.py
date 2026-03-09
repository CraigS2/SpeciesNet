from django.core.management.base import BaseCommand
from django.conf import settings
from species.models import User


class Command(BaseCommand):
    help = 'Create API service account for use with the species-sync REST API'

    def handle(self, *args, **options):
        username = getattr(settings, 'API_SERVICE_USERNAME', 'api_service')
        password = getattr(settings, 'API_SERVICE_PASSWORD', 'changeme_in_production')

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f'{username}@localhost',
                'is_staff': True,
                'is_active': True,
            }
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Created API service user: {username}')
            )
        else:
            # Update password and staff status in case they changed
            user.set_password(password)
            user.is_staff = True
            user.is_active = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Updated API service user: {username}')
            )

        self.stdout.write(f'  username: {username}')
        self.stdout.write(f'  is_staff: {user.is_staff}')
        self.stdout.write(self.style.WARNING(
            'Remember to set a secure password via the API_SERVICE_PASSWORD environment variable '
            'before deploying to production.'
        ))
