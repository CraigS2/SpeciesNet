"""URL configuration for speciesnet project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

"""
from django.conf import settings
from django.contrib import admin
from django.http import Http404
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('species.api.urls')),
    ]

# prevent Site 2 signup url from being accessilble
if settings.SITE_ID != 1:
    urlpatterns += [
        path('signup/', RedirectView.as_view(pattern_name='account_login', permanent=False), name='account_signup'),
    ]

def signup_disabled(request):
    raise Http404

urlpatterns += [
    path('', include('allauth.urls')),
    path('pending-actions/', include('pending_actions.urls')),
    path('', include('species.urls')),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls)), *urlpatterns]
