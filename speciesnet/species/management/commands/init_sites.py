# from django.core.management.base import BaseCommand
# from django.contrib.sites.models import Site
#
# class Command(BaseCommand):
#     help = 'Initialize site records'
#     def handle(self, *args, **options):
#         site1, created = Site.objects.get_or_create(
#             id=1,
#             defaults={
#                 'domain': 'site1.example.com',
#                 'name': 'Site One'
#             }
#         )
#         self.stdout.write(
#             self.style.SUCCESS(f'Site 1: {site1.domain} {"(created)" if created else "(exists)"}')
#         )
#         site2, created = Site.objects.get_or_create(
#             id=2,
#             defaults={
#                 'domain': 'site2.example.com',
#                 'name': 'Site Two'
#             }
#         )
#         self.stdout.write(
#             self.style.SUCCESS(f'Site 2: {site2.domain} {"(created)" if created else "(exists)"}')
#         )

from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from django.conf import settings

class Command(BaseCommand):
    help = 'Initialize site records'

    def handle(self, *args, **options):
        for site_id, config in settings.SITE_CONFIGS.items():
            site, created = Site.objects.update_or_create(
                id=site_id,
                defaults={
                    'domain': config['domain'],
                    'name': config['name']
                }
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created Site {site_id}: {site.domain}')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'Updated Site {site_id}: {site.domain}')
                )        