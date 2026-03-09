from rest_framework.routers import DefaultRouter
from .views import SpeciesSyncViewSet

router = DefaultRouter()
router.register(r'species-sync', SpeciesSyncViewSet, basename='species-sync')

urlpatterns = router.urls
