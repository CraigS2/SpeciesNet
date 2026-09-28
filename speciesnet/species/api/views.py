import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from django.urls import reverse
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from species.models import (
    Species,
    CaresRegistration,
    SpeciesInstance,
    User,
    BapYear,
    BapSubmission,
    BapLeaderboard,
)
from .serializers import SpeciesSyncSerializer, RegistrationSyncSerializer, RegistrationStatusSyncSerializer
from .authentication import ClubApiKeyAuthentication, HasAuthenticatedClub

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


def _serialize_species_instance(request, instance, name=None, url_name='speciesInstance', url_pk=None):
    photo_url = None
    if instance.aquarist_species_image:
        photo_url = request.build_absolute_uri(instance.aquarist_species_image.url)
    return {
        'name': name if name is not None else instance.name,
        'url': request.build_absolute_uri(reverse(url_name, args=[url_pk if url_pk is not None else instance.pk])),
        'photo_url': photo_url,
        'have_spawned': instance.have_spawned,
        'have_reared_fry': instance.have_reared_fry,
        'young_available': instance.young_available,
    }


class ClubAdminBaseApiView(APIView):
    authentication_classes = [ClubApiKeyAuthentication]
    permission_classes = [HasAuthenticatedClub]

    def _club_members_qs(self):
        club = self.request.club
        return User.objects.filter(
            user_club_members__club=club,
            is_proxy=False,
        ).distinct().order_by('username')

    def _resolve_member(self):
        member_value = self.request.query_params.get('member', '').strip()
        if not member_value:
            return None

        club_members = self._club_members_qs()
        by_username = club_members.filter(username=member_value).first()
        if by_username:
            return by_username
        return club_members.filter(email__iexact=member_value).first()

    @staticmethod
    def _full_name(user):
        return user.get_full_name() or user.username


class ClubAdminMembersView(ClubAdminBaseApiView):
    def get(self, request):
        members = self._club_members_qs()
        results = [
            {
                'username': member.username,
                'full_name': self._full_name(member),
                'email': member.email,
            }
            for member in members
        ]
        return Response({'results': results}, status=status.HTTP_200_OK)


class ClubAdminSpeciesInstancesView(ClubAdminBaseApiView):
    def get(self, request):
        member = self._resolve_member()
        if not member:
            return Response({'results': []}, status=status.HTTP_200_OK)

        instances = SpeciesInstance.objects.filter(
            user=member,
            user__user_club_members__club=request.club,
            currently_keep=True,
        ).select_related('species')
        results = [_serialize_species_instance(request, instance) for instance in instances]
        return Response({'results': results}, status=status.HTTP_200_OK)


class ClubAdminCaresSpeciesView(ClubAdminBaseApiView):
    def get(self, request):
        member = self._resolve_member()
        if not member:
            return Response({'results': []}, status=status.HTTP_200_OK)

        instances = SpeciesInstance.objects.filter(
            user=member,
            user__user_club_members__club=request.club,
            species__render_cares=True,
            currently_keep=True,
        ).select_related('species').order_by('species__name', 'id')

        registered_species_ids = set(
            CaresRegistration.objects.filter(
                species_id__in={instance.species_id for instance in instances},
                aquarist_email__iexact=member.email,
            ).values_list('species_id', flat=True)
        )

        results = []
        seen_species_ids = set()
        for instance in instances:
            if instance.species_id in seen_species_ids:
                continue
            seen_species_ids.add(instance.species_id)
            row = _serialize_species_instance(request, instance, name=instance.species.name, url_name='species', url_pk=instance.species_id)
            row['cares_registered'] = instance.species_id in registered_species_ids
            results.append(row)

        return Response({'results': results}, status=status.HTTP_200_OK)


class ClubAdminCaresSpeciesInstancesView(ClubAdminBaseApiView):
    def get(self, request):
        member = self._resolve_member()
        if not member:
            return Response({'results': []}, status=status.HTTP_200_OK)

        instances = SpeciesInstance.objects.filter(
            user=member,
            user__user_club_members__club=request.club,
            species__render_cares=True,
            currently_keep=True,
        ).select_related('species')

        results = [_serialize_species_instance(request, instance) for instance in instances]
        return Response({'results': results}, status=status.HTTP_200_OK)


class ClubAdminBapSubmissionsView(ClubAdminBaseApiView):
    def get(self, request):
        club = request.club
        if not club.is_bap_club:
            return Response({'results': []}, status=status.HTTP_200_OK)

        open_bap_year = BapYear.objects.get_open(club)
        if not open_bap_year:
            return Response({'results': []}, status=status.HTTP_200_OK)

        submissions = BapSubmission.objects.filter(
            club=club,
            bap_year=open_bap_year,
        ).exclude(aquarist__is_proxy=True).select_related('aquarist', 'species', 'speciesInstance__species')

        results = []
        for submission in submissions:
            species_name = ''
            if submission.species:
                species_name = submission.species.name
            elif submission.speciesInstance and submission.speciesInstance.species:
                species_name = submission.speciesInstance.species.name

            aquarist = submission.aquarist
            results.append(
                {
                    'species_name': species_name,
                    'username': aquarist.username if aquarist else '',
                    'full_name': self._full_name(aquarist) if aquarist else '',
                    'email': aquarist.email if aquarist else '',
                }
            )

        return Response({'results': results}, status=status.HTTP_200_OK)


class ClubAdminBapLeaderboardView(ClubAdminBaseApiView):
    def get(self, request):
        club = request.club
        if not club.is_bap_club:
            return Response({'results': []}, status=status.HTTP_200_OK)

        open_bap_year = BapYear.objects.get_open(club)
        if not open_bap_year:
            return Response({'results': []}, status=status.HTTP_200_OK)

        entries = BapLeaderboard.objects.filter(
            club=club,
            bap_year=open_bap_year,
        ).exclude(aquarist__is_proxy=True).select_related('aquarist').order_by('-points', 'id')

        results = [
            {
                'points': entry.points,
                'username': entry.aquarist.username if entry.aquarist else '',
                'full_name': self._full_name(entry.aquarist) if entry.aquarist else '',
                'email': entry.aquarist.email if entry.aquarist else '',
            }
            for entry in entries
        ]
        return Response({'results': results}, status=status.HTTP_200_OK)
