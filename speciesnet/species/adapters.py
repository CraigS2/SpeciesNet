"""
Minimal custom allauth adapter for SpeciesNet.

Overrides DefaultAccountAdapter only to provide a graceful user-facing
message when an inactive proxy account attempts to use the standard login
form before completing account activation.

All other allauth behaviour (signup, email, social auth) is unchanged.
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


class SpeciesNetAccountAdapter(DefaultAccountAdapter):

    def authentication_failed(self, request, **kwargs):
        """
        Called by allauth when login fails.  If the submitted credentials match
        an inactive proxy account, show a specific message directing the user to
        check their invitation email rather than the generic 'invalid credentials'
        message.
        """
        credentials = kwargs.get('credentials') or {}
        email = (credentials.get('email') or '').strip().lower()

        if email:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(email=email)
                if not user.is_active and user.is_proxy:
                    logger.info(
                        'Inactive proxy account attempted login: email=%s', email
                    )
                    messages.error(
                        request,
                        'This account has not been activated yet. '
                        'Please check your email for an invitation link to set your password.',
                    )
                    return redirect('login')
            except User.DoesNotExist:
                pass

        return super().authentication_failed(request, **kwargs)
