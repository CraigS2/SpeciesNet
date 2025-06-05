from django.conf import settings # import the settings file

def google_oauth(request):
    return {'GOOGLE_OAUTH_CLIENT_ID': settings.GOOGLE_OAUTH_CLIENT_ID}
    #return {'GOOGLE_OAUTH_LINK': settings.GOOGLE_OAUTH_LINK}

