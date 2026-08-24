from django.conf import settings
from rest_framework import serializers
from species.models import Species, CaresRegistration


class SpeciesSyncSerializer(serializers.ModelSerializer):
    """
    Serializer for CARES species synchronization.
    Exposes only the fields relevant to CARES sync (Site2 → Site1).
    """

    class Meta:
        model = Species
        fields = [
            'name',
            'alt_name',
            'description',
            'global_region',
            'local_distribution',
            'cares_family',
            'iucn_red_list',
            'cares_classification',
            'render_cares',
            'created',
            'lastUpdated',
        ]
        read_only_fields = fields


class RegistrationSyncSerializer(serializers.ModelSerializer):
    """
    Serializer for Site1 → Site2 new-registration sync.

    Exposes the same fields used by the CSV importer
    (_import_cares_registrations_from_asn) so both paths share identical
    field semantics.  The API consumer (Site2's RegistrationSyncService)
    stores the ``id`` value as ``external_id`` on the Site2 registration,
    creating the durable correlation key for the reverse status-update sync.
    """

    # Resolve FK relations to plain strings, mirroring the CSV export
    species = serializers.CharField(source='species.name', default='')
    collection_location = serializers.SerializerMethodField()
    verification_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = CaresRegistration
        fields = [
            'id',
            'aquarist_name',
            'aquarist_email',
            'species',
            'species_source',
            'collection_location',
            'year_acquired',
            'species_has_spawned',
            'young_available',
            'offspring_shared',
            'date_requested',
            'verification_photo_url',
        ]
        read_only_fields = fields

    def get_collection_location(self, obj):
        if obj.collection_location:
            return obj.collection_location.name
        return ''

    def get_verification_photo_url(self, obj):
        if not obj.verification_photo:
            return ''
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.verification_photo.url)
        # Fall back to settings-based URL construction (mirrors _build_media_url)
        site_domain = getattr(settings, 'SITE_DOMAIN', '')
        if site_domain:
            return f'https://{site_domain}{obj.verification_photo.url}'
        site1_url = getattr(settings, 'SITE1_URL', '').rstrip('/')
        if site1_url:
            return f'{site1_url}{obj.verification_photo.url}'
        return obj.verification_photo.url


class RegistrationStatusSyncSerializer(serializers.ModelSerializer):
    """
    Serializer for Site2 → Site1 status-update sync.

    Exposes only the fields needed to match and update the Site1 record:
    ``external_id`` (Site1's CaresRegistration.id), ``status``, and
    ``approver_notes``.  Only rows where external_id > 0 and status is
    APRV or DECL are served by the viewset.
    """

    # Include extra context fields for logging/report purposes
    species = serializers.CharField(source='species.name', default='')
    aquarist_name = serializers.CharField(read_only=True)

    class Meta:
        model = CaresRegistration
        fields = [
            'external_id',
            'status',
            'approver_notes',
            'species',
            'aquarist_name',
            'lastUpdated',
        ]
        read_only_fields = fields
