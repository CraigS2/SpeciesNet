from django.urls import path

from .views import ClubInviteOptOutView, PendingActionConfirmView, ProxyActivationView, pending_action_confirmation_complete

urlpatterns = [
    path('confirm/completed/', pending_action_confirmation_complete, name='pending_action_confirmation_complete'),
    path('confirm/<str:token>/', PendingActionConfirmView.as_view(), name='pending_action_confirm'),
    path('activate/<str:token>/', ProxyActivationView.as_view(), name='proxy_activate'),
    path('opt-out/<str:token>/', ClubInviteOptOutView.as_view(), name='club_invite_opt_out'),
]
