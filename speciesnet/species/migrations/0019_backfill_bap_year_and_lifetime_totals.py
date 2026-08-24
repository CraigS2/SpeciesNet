from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    AquaristClub = apps.get_model('species', 'AquaristClub')
    BapYear = apps.get_model('species', 'BapYear')
    BapSubmission = apps.get_model('species', 'BapSubmission')
    BapLeaderboard = apps.get_model('species', 'BapLeaderboard')
    BapLifetimeTotal = apps.get_model('species', 'BapLifetimeTotal')

    today = timezone.localdate()

    # 1) Initial BapYear per BAP-enabled club from legacy start/end dates
    for club in AquaristClub.objects.filter(is_bap_club=True).exclude(bap_start_date__isnull=True).exclude(bap_end_date__isnull=True):
        year_label = club.bap_end_date.year
        defaults = {
            'name': f'{year_label} BAP Year',
            'start_date': club.bap_start_date,
            'end_date': club.bap_end_date,
            'status': 'OPEN' if club.bap_end_date >= today else 'CLSD',
        }
        bap_year, _ = BapYear.objects.get_or_create(club=club, year_label=year_label, defaults=defaults)
        if bap_year.status == 'CLSD' and bap_year.closed_at is None:
            bap_year.closed_at = timezone.now()
            bap_year.save(update_fields=['closed_at'])

    # 2) Backfill submission species from speciesInstance.species and bap_year link from year label
    for sub in BapSubmission.objects.select_related('speciesInstance', 'club').all():
        update_fields = []
        if sub.species_id is None and sub.speciesInstance_id:
            si = sub.speciesInstance
            if si and si.species_id:
                sub.species_id = si.species_id
                update_fields.append('species_id')
        if sub.bap_year_id is None and sub.club_id and sub.year:
            by = BapYear.objects.filter(club_id=sub.club_id, year_label=sub.year).first()
            if by:
                sub.bap_year_id = by.id
                update_fields.append('bap_year_id')
        if update_fields:
            sub.save(update_fields=update_fields)

    # 3) Backfill leaderboard bap_year from club/year
    for lb in BapLeaderboard.objects.filter(bap_year__isnull=True).exclude(club__isnull=True):
        by = BapYear.objects.filter(club_id=lb.club_id, year_label=lb.year).first()
        if by:
            lb.bap_year_id = by.id
            lb.save(update_fields=['bap_year_id'])

    # 4) Backfill BapLifetimeTotal from approved submissions
    approved = BapSubmission.objects.filter(status='APRV').select_related('species', 'club', 'aquarist', 'bap_year').order_by('created')
    grouped = {}
    for sub in approved:
        if not sub.aquarist_id or not sub.club_id:
            continue
        key = (sub.aquarist_id, sub.club_id)
        if key not in grouped:
            grouped[key] = {
                'species_ids': set(),
                'cares_species_ids': set(),
                'points': 0,
                'first_year': None,
                'last_year': None,
            }
        bucket = grouped[key]
        if sub.species_id:
            bucket['species_ids'].add(sub.species_id)
            if getattr(sub.species, 'render_cares', False):
                bucket['cares_species_ids'].add(sub.species_id)
        bucket['points'] += sub.points or 0
        if sub.bap_year_id:
            if bucket['first_year'] is None:
                bucket['first_year'] = sub.bap_year_id
            bucket['last_year'] = sub.bap_year_id

    for (aquarist_id, club_id), bucket in grouped.items():
        BapLifetimeTotal.objects.update_or_create(
            aquarist_id=aquarist_id,
            club_id=club_id,
            defaults={
                'species_count': len(bucket['species_ids']),
                'cares_species_count': len(bucket['cares_species_ids']),
                'points': bucket['points'],
                'first_award_year_id': bucket['first_year'],
                'last_award_year_id': bucket['last_year'],
            }
        )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('species', '0018_smpleaderboard_smplifetimetotal_smpsubmission_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
