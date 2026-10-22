"""
Tests for views_cares.caresSpecies: the show_iucn_assessment display logic.
"""

from django.test import TestCase
from django.urls import reverse

from species.models import Species, User


def _make_user(email='creator@example.com', username='creator'):
    return User.objects.create_user(email=email, username=username, password='pass')


class CaresSpeciesIucnDisplayTests(TestCase):

    def setUp(self):
        self.user = _make_user()

    def _make_species(self, cares_family, iucn_red_list):
        return Species.objects.create(
            name='Test species', category='CIC', created_by=self.user,
            cares_family=cares_family, iucn_red_list=iucn_red_list,
        )

    def test_hides_iucn_for_lake_victoria_cichlids_even_with_real_rating(self):
        species = self._make_species(
            Species.CaresFamily.LV_CICHLIDS, Species.IucnRedList.ENDANGERED,
        )
        response = self.client.get(reverse('caresSpecies', args=[species.pk]))
        self.assertFalse(response.context['show_iucn_assessment'])

    def test_still_shows_iucn_for_other_families(self):
        species = self._make_species(
            Species.CaresFamily.EA_CICHLIDS, Species.IucnRedList.ENDANGERED,
        )
        response = self.client.get(reverse('caresSpecies', args=[species.pk]))
        self.assertTrue(response.context['show_iucn_assessment'])

    def test_lake_victoria_cichlids_still_hidden_when_undefined(self):
        """Undefined rating is already hidden on its own - confirm the family
        check doesn't accidentally flip that back on."""
        species = self._make_species(
            Species.CaresFamily.LV_CICHLIDS, Species.IucnRedList.UNDEFINED,
        )
        response = self.client.get(reverse('caresSpecies', args=[species.pk]))
        self.assertFalse(response.context['show_iucn_assessment'])
