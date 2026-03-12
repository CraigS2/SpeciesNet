from django.core.management.base import BaseCommand
from django.conf import settings
from species.models import User


class Command(BaseCommand):
    help = 'Create API service account for use with the species-sync REST API'

    def handle(self, *args, **options):
        email = getattr(settings, 'API_SERVICE_EMAIL', 'api_service@localhost')
        password = getattr(settings, 'API_SERVICE_PASSWORD', 'changeme_in_production')

        # Derive a username from the email local part (before '@')
        username = email.split('@')[0]

        # Look up by email because USERNAME_FIELD = 'email' on the custom User model.
        # HTTP Basic Authentication also uses the email as the credential, not the username.
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'is_staff': True,
                'is_active': True,
            }
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Created API service user: {email}')
            )
        else:
            # Update password and staff status in case they changed
            user.set_password(password)
            user.is_staff = True
            user.is_active = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Updated API service user: {email}')
            )

        self.stdout.write(f'  email   : {email}')
        self.stdout.write(f'  username: {user.username}')
        self.stdout.write(f'  is_staff: {user.is_staff}')
        self.stdout.write(self.style.WARNING(
            'Remember to set a secure password via the API_SERVICE_PASSWORD environment variable '
            'before deploying to production.'
        ))
