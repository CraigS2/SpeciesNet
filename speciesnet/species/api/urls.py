from rest_framework.routers import DefaultRouter
from .views import SpeciesSyncViewSet, RegistrationSyncViewSet, RegistrationStatusSyncViewSet, SpeciesInstanceSyncViewSet

router = DefaultRouter()
router.register(r'species-sync', SpeciesSyncViewSet, basename='species-sync')
router.register(r'registrations-sync', RegistrationSyncViewSet, basename='registrations-sync')
router.register(r'registrations-status-sync', RegistrationStatusSyncViewSet, basename='registrations-status-sync')
router.register(r'species-instance-sync', SpeciesInstanceSyncViewSet, basename='species-instance-sync')

urlpatterns = router.urls
