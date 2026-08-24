import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from species.models import Species, CaresRegistration, SpeciesInstance
from .serializers import (
    SpeciesSyncSerializer, RegistrationSyncSerializer, RegistrationStatusSyncSerializer,
    SpeciesInstanceSyncSerializer,
)
from .authentication import ClubApiKeyAuthentication
from .permissions import IsBapClub

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


class RegistrationSyncViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API viewset for Site1 → Site2 new-registration sync.

    Exposes OPEN CaresRegistration rows created on Site1 so that Site2's
    RegistrationSyncService can pull them and create corresponding records
    on Site2 (storing Site1's ``id`` as ``external_id``).

    Endpoints (Site1 only):
        GET /api/registrations-sync/                         – paginated list
        GET /api/registrations-sync/?since=<ISO_DATETIME>    – incremental filter
        GET /api/registrations-sync/stats/                   – summary counts
    """

    serializer_class = RegistrationSyncSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = CaresRegistration.objects.filter(
            status=CaresRegistration.CaresRegistrationStatus.OPEN,
        ).order_by('date_requested')

        since_param = self.request.query_params.get('since')
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                qs = qs.filter(date_requested__gte=since_dt)
                logger.info('registrations-sync list filtered by since=%s', since_param)
            else:
                logger.warning('registrations-sync: invalid since parameter "%s" ignored', since_param)

        return qs

    def list(self, request, *args, **kwargs):
        logger.info('registrations-sync list requested by user=%s', request.user.username)
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Return statistics about OPEN registrations available for sync."""
        logger.info('registrations-sync stats requested by user=%s', request.user.username)
        total_open = CaresRegistration.objects.filter(
            status=CaresRegistration.CaresRegistrationStatus.OPEN,
        ).count()

        since_param = request.query_params.get('since')
        recent_count = None
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                recent_count = CaresRegistration.objects.filter(
                    status=CaresRegistration.CaresRegistrationStatus.OPEN,
                    date_requested__gte=since_dt,
                ).count()

        data = {
            'total_open_registrations': total_open,
            'server_time': timezone.now().isoformat(),
        }
        if recent_count is not None:
            data['since'] = since_param
            data['since_count'] = recent_count

        return Response(data, status=status.HTTP_200_OK)


class RegistrationStatusSyncViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API viewset for Site2 → Site1 status-update sync.

    Exposes CaresRegistration rows on Site2 where external_id > 0 and
    status is APRV or DECL, so that Site1's RegistrationStatusSyncService
    can pull status changes and apply them back to the original Site1 records.

    Endpoints (Site2 only):
        GET /api/registrations-status-sync/                         – paginated list
        GET /api/registrations-status-sync/?since=<ISO_DATETIME>    – incremental filter
        GET /api/registrations-status-sync/stats/                   – summary counts
    """

    serializer_class = RegistrationStatusSyncSerializer
    permission_classes = [IsAdminUser]

    ACCEPTED_STATUSES = {
        CaresRegistration.CaresRegistrationStatus.APPROVED,
        CaresRegistration.CaresRegistrationStatus.DECLINED,
    }

    def get_queryset(self):
        qs = CaresRegistration.objects.filter(
            external_id__gt=0,
            status__in=self.ACCEPTED_STATUSES,
        ).order_by('lastUpdated')

        since_param = self.request.query_params.get('since')
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                qs = qs.filter(lastUpdated__gte=since_dt)
                logger.info('registrations-status-sync list filtered by since=%s', since_param)
            else:
                logger.warning('registrations-status-sync: invalid since parameter "%s" ignored', since_param)

        return qs

    def list(self, request, *args, **kwargs):
        logger.info('registrations-status-sync list requested by user=%s', request.user.username)
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Return statistics about decided registrations available for status sync."""
        logger.info('registrations-status-sync stats requested by user=%s', request.user.username)
        total = CaresRegistration.objects.filter(
            external_id__gt=0,
            status__in=self.ACCEPTED_STATUSES,
        ).count()

        since_param = request.query_params.get('since')
        recent_count = None
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                recent_count = CaresRegistration.objects.filter(
                    external_id__gt=0,
                    status__in=self.ACCEPTED_STATUSES,
                    lastUpdated__gte=since_dt,
                ).count()

        data = {
            'total_decided_registrations': total,
            'server_time': timezone.now().isoformat(),
        }
        if recent_count is not None:
            data['since'] = since_param
            data['since_count'] = recent_count

        return Response(data, status=status.HTTP_200_OK)


class SpeciesInstanceSyncViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API viewset for the per-club BAP species-instance report sync.

    Authenticated via a club-generated API key (``X-Club-Api-Key`` header;
    see ``ClubApiKeyAuthentication``) rather than the shared, staff-level
    service account used by the other sync endpoints in this module — each
    club admin manages their own key (generate/revoke) from the club edit
    page. Only clubs with ``is_bap_club=True`` are permitted (``IsBapClub``).

    Only returns SpeciesInstance rows belonging to members of the
    authenticated club where ``currently_keep=True`` and
    ``cares_registered=True``. No BAP-year filtering/annotation is applied
    (the current-year resolution has a known bug that is explicitly out of
    scope for this endpoint — see PR discussion / assumptions list).

    Endpoints:
        GET /api/species-instance-sync/                       - list (paginated)
        GET /api/species-instance-sync/?since=<ISO_DATETIME>  - filter by lastUpdated
        GET /api/species-instance-sync/stats/                 - sync statistics
    """

    authentication_classes = [ClubApiKeyAuthentication]
    permission_classes = [IsBapClub]
    serializer_class = SpeciesInstanceSyncSerializer

    def _base_queryset(self):
        club = self.request.club
        return SpeciesInstance.objects.filter(
            user__user_club_members__club=club,
            currently_keep=True,
            cares_registered=True,
        ).distinct().order_by('lastUpdated')

    def get_queryset(self):
        queryset = self._base_queryset()

        since_param = self.request.query_params.get('since')
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                queryset = queryset.filter(lastUpdated__gte=since_dt)
                logger.info('species-instance-sync list filtered by since=%s', since_param)
            else:
                logger.warning('species-instance-sync: invalid since parameter "%s" ignored', since_param)

        return queryset

    def list(self, request, *args, **kwargs):
        logger.info('species-instance-sync list requested by club=%s', request.club.name)
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Return statistics about the reportable species instances for this club."""
        logger.info('species-instance-sync stats requested by club=%s', request.club.name)
        total = self._base_queryset().count()

        since_param = request.query_params.get('since')
        recent_count = None
        if since_param:
            since_dt = _parse_since_param(since_param)
            if since_dt is not None:
                recent_count = self._base_queryset().filter(lastUpdated__gte=since_dt).count()

        data = {
            'club': request.club.name,
            'total_species_instances': total,
            'server_time': timezone.now().isoformat(),
        }
        if recent_count is not None:
            data['since'] = since_param
            data['since_count'] = recent_count

        return Response(data, status=status.HTTP_200_OK)
