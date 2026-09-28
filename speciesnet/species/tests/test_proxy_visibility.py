"""
Tests that proxy users (User.is_proxy=True) and their SpeciesInstances —
club-internal bookkeeping created by the BAP import workflow for
non-member auction sellers — never surface on general public pages:
species search, the species detail page, and the aquarists directory.

Two categories are intentionally exempt from proxy filtering, since they
show the full data set (including proxies) on purpose but only to staff:
  - the species-instance photo/video/log galleries in views_tools.py
    (admin tools, not public/club-scoped pages)
  - the CSV export views (exportAquarists / exportSpeciesInstances)
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from species.models import (
    Species, SpeciesInstance, SpeciesInstanceLogEntry,
)

User = get_user_model()


def _make_user(email, username=None, is_proxy=False):
    u = User(email=email, username=username or email.split('@')[0], is_proxy=is_proxy)
    u.set_password('testpass123')
    u.save()
    return u


def _make_species(name):
    return Species.objects.create(name=name, category='FW', global_region='AFR')


class SpeciesPageProxyVisibilityTests(TestCase):

    def setUp(self):
        self.species = _make_species('Aulonocara jacobfreibergi')
        self.real_user = _make_user('real@test.com', 'realkeeper')
        self.proxy_user = _make_user('proxy@test.com', 'proxykeeper', is_proxy=True)
        SpeciesInstance.objects.create(
            name='real instance', user=self.real_user, species=self.species, currently_keep=True,
        )
        SpeciesInstance.objects.create(
            name='proxy instance', user=self.proxy_user, species=self.species, currently_keep=True,
        )

    def test_real_user_shown(self):
        response = self.client.get(reverse('species', args=[self.species.id]))
        self.assertContains(response, 'realkeeper')

    def test_proxy_user_not_shown(self):
        response = self.client.get(reverse('species', args=[self.species.id]))
        self.assertNotContains(response, 'proxykeeper')


class SpeciesSearchProxyVisibilityTests(TestCase):

    def setUp(self):
        self.species = _make_species('Symphysodon discus')
        self.real_user = _make_user('real2@test.com', 'realkeeper2')
        self.proxy_user = _make_user('proxy2@test.com', 'proxykeeper2', is_proxy=True)

    def test_instance_count_excludes_proxy_users(self):
        SpeciesInstance.objects.create(
            name='real', user=self.real_user, species=self.species, currently_keep=True,
        )
        SpeciesInstance.objects.create(
            name='proxy', user=self.proxy_user, species=self.species, currently_keep=True,
        )
        response = self.client.get(reverse('speciesSearch'))
        result = next(s for s in response.context['species_list'] if s.pk == self.species.pk)
        self.assertEqual(result.instance_count, 1)

    def test_instance_count_excludes_not_currently_kept(self):
        SpeciesInstance.objects.create(
            name='current', user=self.real_user, species=self.species, currently_keep=True,
        )
        SpeciesInstance.objects.create(
            name='former', user=self.real_user, species=self.species, currently_keep=False,
        )
        response = self.client.get(reverse('speciesSearch'))
        result = next(s for s in response.context['species_list'] if s.pk == self.species.pk)
        self.assertEqual(result.instance_count, 1)


class AquaristsDirectoryProxyVisibilityTests(TestCase):

    def setUp(self):
        self.real_user = _make_user('real3@test.com', 'realkeeper3')
        self.proxy_user = _make_user('proxy3@test.com', 'proxykeeper3', is_proxy=True)
        self.species = _make_species('Melanotaenia boesemani')

    def test_proxy_user_excluded_from_directory(self):
        response = self.client.get(reverse('aquarists'))
        usernames = [u.username for u in response.context['aquarist_list']]
        self.assertIn('realkeeper3', usernames)
        self.assertNotIn('proxykeeper3', usernames)

    def test_recent_species_instances_excludes_proxy_and_not_current(self):
        SpeciesInstance.objects.create(
            name='real current', user=self.real_user, species=self.species, currently_keep=True,
        )
        SpeciesInstance.objects.create(
            name='real former', user=self.real_user, species=self.species, currently_keep=False,
        )
        SpeciesInstance.objects.create(
            name='proxy current', user=self.proxy_user, species=self.species, currently_keep=True,
        )
        response = self.client.get(reverse('aquarists'))
        names = [si.name for si in response.context['recent_speciesInstances']]
        self.assertIn('real current', names)
        self.assertNotIn('real former', names)
        self.assertNotIn('proxy current', names)


class SpeciesInstanceGalleriesAreAdminOnlyTests(TestCase):
    """
    speciesInstancesWithPhotos/Videos/Logs are admin tools (per the
    views_tools.py module docstring), not public/club-scoped pages — they
    intentionally show proxy accounts too, but only to staff.
    """

    def setUp(self):
        self.real_user = _make_user('real4@test.com', 'realkeeper4')
        self.proxy_user = _make_user('proxy4@test.com', 'proxykeeper4', is_proxy=True)
        self.staff_user = _make_user('staff4@test.com', 'staff4')
        self.staff_user.is_staff = True
        self.staff_user.save()
        self.species = _make_species('Pterophyllum scalare')
        self.client = Client()

    def test_photos_gallery_requires_staff(self):
        self.client.force_login(self.real_user)
        response = self.client.get(reverse('speciesInstancesWithPhotos'))
        self.assertEqual(response.status_code, 403)

    def test_photos_gallery_includes_proxy_for_staff(self):
        SpeciesInstance.objects.create(
            name='real photo', user=self.real_user, species=self.species,
            aquarist_species_image='images/real.jpg',
        )
        SpeciesInstance.objects.create(
            name='proxy photo', user=self.proxy_user, species=self.species,
            aquarist_species_image='images/proxy.jpg',
        )
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('speciesInstancesWithPhotos'))
        names = [si.name for si in response.context['si_with_photos']]
        self.assertIn('real photo', names)
        self.assertIn('proxy photo', names)

    def test_videos_gallery_requires_staff(self):
        self.client.force_login(self.real_user)
        response = self.client.get(reverse('speciesInstancesWithVideos'))
        self.assertEqual(response.status_code, 403)

    def test_videos_gallery_includes_proxy_for_staff(self):
        SpeciesInstance.objects.create(
            name='real video', user=self.real_user, species=self.species,
            aquarist_species_video_url='https://youtube.com/real',
        )
        SpeciesInstance.objects.create(
            name='proxy video', user=self.proxy_user, species=self.species,
            aquarist_species_video_url='https://youtube.com/proxy',
        )
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('speciesInstancesWithVideos'))
        names = [si.name for si in response.context['speciesInstances']]
        self.assertIn('real video', names)
        self.assertIn('proxy video', names)

    def test_logs_gallery_requires_staff(self):
        self.client.force_login(self.real_user)
        response = self.client.get(reverse('speciesInstancesWithLogs'))
        self.assertEqual(response.status_code, 403)

    def test_logs_gallery_includes_proxy_for_staff(self):
        real_si = SpeciesInstance.objects.create(
            name='real log', user=self.real_user, species=self.species,
        )
        proxy_si = SpeciesInstance.objects.create(
            name='proxy log', user=self.proxy_user, species=self.species,
        )
        SpeciesInstanceLogEntry.objects.create(
            name='entry1', speciesInstance=real_si, log_entry_notes='notes',
        )
        SpeciesInstanceLogEntry.objects.create(
            name='entry2', speciesInstance=proxy_si, log_entry_notes='notes',
        )
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('speciesInstancesWithLogs'))
        names = [si.name for si in response.context['speciesInstances']]
        self.assertIn('real log', names)
        self.assertIn('proxy log', names)


class ExportPermissionTests(TestCase):
    """Full CSV exports intentionally include proxy data — but only staff may fetch them."""

    def setUp(self):
        self.regular_user = _make_user('regular5@test.com', 'regular5')
        self.staff_user = _make_user('staff5@test.com', 'staff5')
        self.staff_user.is_staff = True
        self.staff_user.save()

    def test_export_aquarists_requires_login(self):
        response = self.client.get(reverse('exportAquarists'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_export_aquarists_regular_user_forbidden(self):
        self.client.login(email='regular5@test.com', password='testpass123')
        response = self.client.get(reverse('exportAquarists'))
        self.assertEqual(response.status_code, 403)

    def test_export_aquarists_staff_allowed(self):
        self.client.login(email='staff5@test.com', password='testpass123')
        response = self.client.get(reverse('exportAquarists'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

    def test_export_species_instances_regular_user_forbidden(self):
        self.client.login(email='regular5@test.com', password='testpass123')
        response = self.client.get(reverse('exportSpeciesInstances'))
        self.assertEqual(response.status_code, 403)

    def test_export_species_instances_staff_allowed(self):
        self.client.login(email='staff5@test.com', password='testpass123')
        response = self.client.get(reverse('exportSpeciesInstances'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
