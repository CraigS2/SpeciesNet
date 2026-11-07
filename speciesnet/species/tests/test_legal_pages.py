"""
Tests for the legal notice / terms of use / privacy pages added for both
sites, and the site-wide footer in templates/main.html.
"""
from django.conf import settings
from django.test import TestCase, override_settings


class FooterTest(TestCase):
    """
    The footer renders on every page via templates/main.html. Its content
    comes from CURRENT_SITE_CONFIG['footer_copyright'] / ['footer_shows_terms_license_privacy'],
    which settings.py now sources from the COPYRIGHT_TEXT / DISPLAY_TERMS_LICENSE_PRIVACY
    env vars (same vars regardless of SITE_ID - each site is deployed from
    its own .env, so only one of SITE_CONFIGS[1]/[2] is ever actually used
    per process). Tests here override CURRENT_SITE_CONFIG directly rather
    than the env vars, since settings.py only reads them once at import time.
    """

    def test_footer_shows_configured_copyright_text(self):
        custom_config = {**settings.CURRENT_SITE_CONFIG, 'footer_copyright': 'TEST_COPYRIGHT_LINE'}
        with override_settings(CURRENT_SITE_CONFIG=custom_config):
            response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TEST_COPYRIGHT_LINE')

    def test_footer_shows_terms_license_privacy_links_when_enabled(self):
        custom_config = {**settings.CURRENT_SITE_CONFIG, 'footer_shows_terms_license_privacy': True}
        with override_settings(CURRENT_SITE_CONFIG=custom_config):
            response = self.client.get('/')
        self.assertContains(response, '/terms/')
        self.assertContains(response, '/license/')
        self.assertContains(response, '/privacy/')

    def test_footer_hides_terms_license_privacy_links_when_disabled(self):
        custom_config = {**settings.CURRENT_SITE_CONFIG, 'footer_shows_terms_license_privacy': False}
        with override_settings(CURRENT_SITE_CONFIG=custom_config):
            response = self.client.get('/')
        self.assertNotContains(response, '/terms/')
        self.assertNotContains(response, '/license/')
        self.assertNotContains(response, '/privacy/')

    def test_footer_renders_on_about_us_page_too(self):
        """Not just the home page - the footer lives in the shared base
        template, so any page extending it gets one."""
        custom_config = {**settings.CURRENT_SITE_CONFIG, 'footer_copyright': 'TEST_COPYRIGHT_LINE'}
        with override_settings(CURRENT_SITE_CONFIG=custom_config):
            response = self.client.get('/about_us/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TEST_COPYRIGHT_LINE')


class LegalPagesTest(TestCase):
    def test_terms_of_use_site1(self):
        response = self.client.get('/terms/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AquaristSpecies.net Terms of Use')
        self.assertContains(response, 'aquaristspecies@gmail.com')

    @override_settings(CURRENT_SITE_CONFIG=settings.SITE_CONFIGS[2])
    def test_terms_of_use_site2(self):
        response = self.client.get('/terms/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CaresSpecies.org Terms of Use')
        self.assertContains(response, 'caresspecies@gmail.com')

    def test_legal_notice_site1_links_to_github(self):
        response = self.client.get('/license/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://github.com/CraigS2/SpeciesNet')
        self.assertContains(response, 'AquaristSpecies.net')
        # Site1's contact/copyright-complaint email is always aquaristspecies@,
        # never caresspecies@ - this page previously had the wrong one.
        self.assertContains(response, 'aquaristspecies@gmail.com')
        self.assertNotContains(response, 'caresspecies@gmail.com')

    @override_settings(CURRENT_SITE_CONFIG=settings.SITE_CONFIGS[2])
    def test_legal_notice_site2_links_to_github(self):
        response = self.client.get('/license/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://github.com/CraigS2/SpeciesNet')
        self.assertContains(response, 'CaresSpecies.org')
        self.assertContains(response, 'caresspecies@gmail.com')

    def test_privacy_policy_site1(self):
        response = self.client.get('/privacy/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AquaristSpecies.net Privacy Policy')
        self.assertContains(response, 'aquaristspecies@gmail.com')
        self.assertNotContains(response, 'caresspecies@gmail.com')

    @override_settings(CURRENT_SITE_CONFIG=settings.SITE_CONFIGS[2])
    def test_privacy_policy_site2(self):
        response = self.client.get('/privacy/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CaresSpecies.org Privacy Policy')
        self.assertContains(response, 'caresspecies@gmail.com')

    def test_terms_links_to_privacy_and_license(self):
        response = self.client.get('/terms/')
        self.assertContains(response, '/privacy/')
        self.assertContains(response, '/license/')

    def test_site1_pages_never_show_caresspecies_email(self):
        """The one bug already found and fixed - guard against it coming back."""
        for path in ('/terms/', '/license/', '/privacy/'):
            response = self.client.get(path)
            self.assertNotContains(response, 'caresspecies@gmail.com', msg_prefix=f'on {path}')


class SiteOwnerDisplayTextTest(TestCase):
    """
    'Who we are'/'Who runs this site' on the Terms/License/Privacy pages
    shows SITE_OWNER_DISPLAY_TEXT (env-configured, default 'Site Owner
    Name') rather than a real name hardcoded in source.
    """

    def test_defaults_to_site_owner_name_on_all_pages_both_sites(self):
        for config in (settings.SITE_CONFIGS[1], settings.SITE_CONFIGS[2]):
            with override_settings(CURRENT_SITE_CONFIG=config):
                for path in ('/terms/', '/license/', '/privacy/'):
                    response = self.client.get(path)
                    self.assertContains(response, 'Site Owner Name', msg_prefix=f'on {path}')
                    self.assertNotContains(response, 'Craig G. Storms', msg_prefix=f'on {path}')

    @override_settings(SITE_OWNER_DISPLAY_TEXT='Configured Owner Name')
    def test_configured_value_overrides_default_on_all_pages(self):
        for path in ('/terms/', '/license/', '/privacy/'):
            response = self.client.get(path)
            self.assertContains(response, 'Configured Owner Name', msg_prefix=f'on {path}')
            self.assertNotContains(response, 'Site Owner Name', msg_prefix=f'on {path}')
