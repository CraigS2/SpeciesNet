from django.urls import path

from .views import PendingActionConfirmView, pending_action_confirmation_complete

urlpatterns = [
    path('confirm/completed/', pending_action_confirmation_complete, name='pending_action_confirmation_complete'),
    path('confirm/<str:token>/', PendingActionConfirmView.as_view(), name='pending_action_confirm'),
]
