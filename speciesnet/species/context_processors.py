from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
import os

def google_oauth(request):
    return {'GOOGLE_OAUTH_LINK': settings.GOOGLE_OAUTH_LINK}

def site_config(request):
    return {
        'site_config': settings.CURRENT_SITE_CONFIG,
    }

def environment_vars(request):
    return {
        'SITE_TITLE': os.environ.get('SITE_TITLE', 'Aquarist Species'),
    }
