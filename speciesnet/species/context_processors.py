from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache

def google_oauth(request):
    return {'GOOGLE_OAUTH_LINK': settings.GOOGLE_OAUTH_LINK}

def site_config(request):
    return {
        'site_config': settings.CURRENT_SITE_CONFIG,
    }

# def site_config(request):
#     """Make site configuration available in all templates"""
#     site = get_current_site(request)
#     cache_key = f'site_config_{site.id}'         # caches config to not hit db for every request
#     config = cache.get(cache_key)
#     if config is None:
#         try:
#             config = site.config
#             cache.set(cache_key, config, 3600)  # Cache for 1 hour
#         except: 
#             config = None
#     return {
#         'site':  site,
#         'site_config': config,
#     }
