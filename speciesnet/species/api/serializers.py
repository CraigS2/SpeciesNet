from rest_framework import serializers
from species.models import Species


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
            'created',
            'lastUpdated',
        ]
        read_only_fields = fields
