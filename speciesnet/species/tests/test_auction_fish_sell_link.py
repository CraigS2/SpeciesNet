"""
Tests for the Site 1 'Sell offspring on Auction.fish' button: the pre-filled
auction.fish new-lot URL and when the speciesInstance page shows it.
"""
from urllib.parse import urlparse, parse_qs

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from species.asn_tools.auction_fish_api import build_auction_fish_new_lot_url
from species.models import Species, SpeciesInstance

User = get_user_model()

BUTTON_TEXT = 'Sell offspring on Auction.fish'


def _params(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


@override_settings(SITE_DOMAIN='aquaristspecies.example.com')
class AuctionFishNewLotUrlTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='breeder', email='breeder@test.com', password='pw')
        self.species = Species.objects.create(
            name='Corydoras paleatus', common_name='Peppered Cory',
            category='CAT', global_region='SAM', created_by=self.user,
        )
        self.si = SpeciesInstance.objects.create(
            name='Corydoras paleatus long-fin', user=self.user, species=self.species, young_available=True,
        )

    def test_base_url_and_fixed_params(self):
        url = build_auction_fish_new_lot_url(self.si)
        self.assertTrue(url.startswith('https://auction.fish/lots/new/?'))
        params = _params(url)
        self.assertEqual(params['i_bred_this_fish'], 'True')
        self.assertEqual(
            params['summernote_description'],
            'Group of young Corydoras paleatus long-fin. Please see my AquaristSpecies.net '
            'species page (reference link) for more information on these fish.',
        )
        self.assertEqual(
            params['reference_link'],
            f'https://aquaristspecies.example.com/speciesInstance/{self.si.pk}/',
        )
        self.assertNotIn('auction', params)
        self.assertNotIn('quantity', params)

    def test_lot_name_uses_instance_name_when_it_fits(self):
        self.assertEqual(_params(build_auction_fish_new_lot_url(self.si))['lot_name'], 'Corydoras paleatus long-fin')

    def test_lot_name_instance_name_exactly_40_chars(self):
        self.si.name = 'x' * 40
        self.assertEqual(_params(build_auction_fish_new_lot_url(self.si))['lot_name'], 'x' * 40)

    def test_lot_name_falls_back_to_species_and_common_name(self):
        self.si.name = 'Corydoras paleatus long-fin from my 2024 spawn'
        self.assertEqual(
            _params(build_auction_fish_new_lot_url(self.si))['lot_name'],
            'Corydoras paleatus - Peppered Cory',
        )

    def test_lot_name_falls_back_to_species_name_when_common_name_too_long(self):
        self.si.name = 'Corydoras paleatus long-fin from my 2024 spawn'
        self.species.common_name = 'Peppered Corydoras Catfish'
        self.assertEqual(_params(build_auction_fish_new_lot_url(self.si))['lot_name'], 'Corydoras paleatus')

    def test_lot_name_falls_back_to_species_name_without_common_name(self):
        self.si.name = 'Corydoras paleatus long-fin from my 2024 spawn'
        self.species.common_name = ''
        self.assertEqual(_params(build_auction_fish_new_lot_url(self.si))['lot_name'], 'Corydoras paleatus')

    def test_lot_name_never_exceeds_40_chars(self):
        self.si.name = 'y' * 60
        self.species.name = 'z' * 50
        self.species.common_name = ''
        self.assertEqual(len(_params(build_auction_fish_new_lot_url(self.si))['lot_name']), 40)

    def test_no_image_param_without_images(self):
        self.assertNotIn('image_url', _params(build_auction_fish_new_lot_url(self.si)))

    def test_image_prefers_young_available_image(self):
        self.si.aquarist_species_image = 'images/2026/01/01/adult.jpg'
        self.si.young_available_image = 'images/2026/01/01/young.jpg'
        self.assertEqual(
            _params(build_auction_fish_new_lot_url(self.si))['image_url'],
            'https://aquaristspecies.example.com/media/images/2026/01/01/young.jpg',
        )

    def test_image_falls_back_to_aquarist_species_image(self):
        self.si.aquarist_species_image = 'images/2026/01/01/adult.jpg'
        self.assertEqual(
            _params(build_auction_fish_new_lot_url(self.si))['image_url'],
            'https://aquaristspecies.example.com/media/images/2026/01/01/adult.jpg',
        )


@override_settings(SITE_ID=1, SITE_DOMAIN='aquaristspecies.example.com')
class SellOffspringButtonTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@test.com', password='pw')
        self.other = User.objects.create_user(username='other', email='other@test.com', password='pw')
        self.species = Species.objects.create(
            name='Corydoras paleatus', category='CAT', global_region='SAM', created_by=self.owner,
        )
        self.si = SpeciesInstance.objects.create(
            name='Corydoras paleatus', user=self.owner, species=self.species, young_available=True,
        )
        self.url = reverse('speciesInstance', args=[self.si.pk])
        self.client = Client()

    def test_owner_with_young_available_sees_button(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, BUTTON_TEXT)
        self.assertContains(response, 'https://auction.fish/lots/new/?')

    def test_hidden_when_young_not_available(self):
        self.si.young_available = False
        self.si.save()
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(self.url), BUTTON_TEXT)

    def test_hidden_for_other_users(self):
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.url), BUTTON_TEXT)

    def test_hidden_for_anonymous(self):
        self.assertNotContains(self.client.get(self.url), BUTTON_TEXT)

    @override_settings(SITE_ID=2)
    def test_hidden_on_site_2(self):
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(self.url), BUTTON_TEXT)
