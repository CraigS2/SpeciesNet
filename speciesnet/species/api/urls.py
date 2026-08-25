from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    SpeciesSyncViewSet,
    RegistrationSyncViewSet,
    RegistrationStatusSyncViewSet,
    ClubAdminMembersView,
    ClubAdminSpeciesKeptView,
    ClubAdminSpeciesInstancesView,
    ClubAdminCaresSpeciesView,
    ClubAdminCaresSpeciesInstancesView,
    ClubAdminBapSubmissionsView,
    ClubAdminBapLeaderboardView,
)

router = DefaultRouter()
router.register(r'species-sync', SpeciesSyncViewSet, basename='species-sync')
router.register(r'registrations-sync', RegistrationSyncViewSet, basename='registrations-sync')
router.register(r'registrations-status-sync', RegistrationStatusSyncViewSet, basename='registrations-status-sync')

urlpatterns = router.urls + [
    path('club-admin/members/', ClubAdminMembersView.as_view(), name='clubAdminMembers'),
    path('club-admin/species-kept/', ClubAdminSpeciesKeptView.as_view(), name='clubAdminSpeciesKept'),
    path('club-admin/species-instances/', ClubAdminSpeciesInstancesView.as_view(), name='clubAdminSpeciesInstances'),
    path('club-admin/cares-species/', ClubAdminCaresSpeciesView.as_view(), name='clubAdminCaresSpecies'),
    path('club-admin/cares-species-instances/', ClubAdminCaresSpeciesInstancesView.as_view(), name='clubAdminCaresSpeciesInstances'),
    path('club-admin/bap-submissions/', ClubAdminBapSubmissionsView.as_view(), name='clubAdminBapSubmissions'),
    path('club-admin/bap-leaderboard/', ClubAdminBapLeaderboardView.as_view(), name='clubAdminBapLeaderboard'),
]
