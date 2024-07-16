from django.conf import settings # import the settings file

def google_oauth(request):
    return {'GOOGLE_OAUTH_LINK': settings.GOOGLE_OAUTH_LINK}
