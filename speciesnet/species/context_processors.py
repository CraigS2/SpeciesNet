from django.conf import settings # import the settings file

# def google_oauth(request):
#     return {'GOOGLE_OAUTH_CLIENT_ID': settings.GOOGLE_OAUTH_CLIENT_ID}
    #return {'GOOGLE_OAUTH_LINK': settings.GOOGLE_OAUTH_LINK}

    ##Construct the redirect_uri that matches your Google Developer Console configuration
    #redirect_uri = request.build_absolute_uri('/accounts/google/login/callback/') # Example with django-allauth

    # Initiate the Google OAuth flow and redirect the user
    # Note: django-allauth handles this logic internally when you use their views/urls
    # You would typically have a URL pattern like:
    # path('accounts/google/login/', GoogleLogin.as_view(), name='google_login')
    # and in your template, the link would be: {% provider_login_url 'google' %}
    # If you are implementing it manually, you'd build the authorization URL and redirect:
    # authorization_url = build_authorization_url(...)
    # return redirect(authorization_url)
    #pass # Use django-allauth's predefined view for simpler integration