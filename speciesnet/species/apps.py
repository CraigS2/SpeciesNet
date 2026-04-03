from django.apps import AppConfig


class SpeciesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'species'

    def ready(self):
        from django.contrib import admin
        from allauth.account.models import EmailAddress
        from .admin import EmailAddressAdmin

        try:
            admin.site.unregister(EmailAddress)
        except admin.sites.NotRegistered:
            pass
        admin.site.register(EmailAddress, EmailAddressAdmin)
