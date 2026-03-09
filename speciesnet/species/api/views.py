import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from species.models import Species
from .serializers import SpeciesSyncSerializer

logger = logging.getLogger(__name__)


def _parse_since_param(since_param):
    """
    Parse a `since` query parameter string into an aware datetime.

    Handles:
    - ISO 8601 datetime strings (with optional timezone)
    - Date-only strings (YYYY-MM-DD), interpreted as midnight UTC
    - '+' sign encoded as space (common in URL query parameters)

    Returns an aware datetime, or None if parsing fails.
    """
    # URL query params decode '+' as space; restore it for timezone offsets
    normalized = since_param.replace(' ', '+')
    dt = parse_datetime(normalized)
    if dt is None:
        parsed_date = parse_date(normalized)
        if parsed_date:
            dt = timezone.datetime(
                parsed_date.year, parsed_date.month, parsed_date.day,
                tzinfo=timezone.utc,
            )
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


class SpeciesSyncViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API viewset for CARES species synchronization.

    Provides endpoints for Site1 to pull CARES species data from Site2.
    Only returns species where render_cares=True.
    Requires staff authentication for all endpoints.

    Endpoints:
        GET /api/species-sync/                          - list all CARES species (paginated)
        GET /api/species-sync/?since=<ISO_DATETIME>     - filter by lastUpdated date
        GET /api/species-sync/stats/                    - sync statistics
    """

    serializer_class = SpeciesSyncSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Species.objects.filter(render_cares=True).order_by('name')

        since_param = self.request.query_params.get('since')
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                queryset = queryset.filter(lastUpdated__gte=since_dt)
                logger.info('species-sync list filtered by since=%s', since_param)
            else:
                logger.warning('species-sync: invalid since parameter "%s" ignored', since_param)

        return queryset

    def list(self, request, *args, **kwargs):
        logger.info('species-sync list requested by user=%s', request.user.username)
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Return statistics about the CARES species available for sync."""
        logger.info('species-sync stats requested by user=%s', request.user.username)
        total_cares = Species.objects.filter(render_cares=True).count()

        since_param = request.query_params.get('since')
        recent_count = None
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                recent_count = Species.objects.filter(
                    render_cares=True, lastUpdated__gte=since_dt
                ).count()

        data = {
            'total_cares_species': total_cares,
            'server_time': timezone.now().isoformat(),
        }
        if recent_count is not None:
            data['updated_since'] = since_param
            data['updated_since_count'] = recent_count

        return Response(data, status=status.HTTP_200_OK)
