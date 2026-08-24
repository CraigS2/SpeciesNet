from rest_framework.routers import DefaultRouter
from .views import SpeciesSyncViewSet, RegistrationSyncViewSet, RegistrationStatusSyncViewSet

router = DefaultRouter()
router.register(r'species-sync', SpeciesSyncViewSet, basename='species-sync')
router.register(r'registrations-sync', RegistrationSyncViewSet, basename='registrations-sync')
router.register(r'registrations-status-sync', RegistrationStatusSyncViewSet, basename='registrations-status-sync')

urlpatterns = router.urls
