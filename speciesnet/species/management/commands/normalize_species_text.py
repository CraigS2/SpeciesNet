"""
PASS1_SCOPE.md section 4: one-time cleanup of existing quote/whitespace
contamination in Species and SpeciesInstance text fields.

Dry run by default - pass --apply to write changes. See the "Rollout order"
section of PASS1_SCOPE.md: run this on CSO first, review and merge any
reported collisions by hand, --apply, then repeat on ASN, before deploying
the Species.name unique migration.
"""

import csv
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from species.models import (
    Species, SpeciesInstance, CaresRegistration, BapSpecies,
    SpeciesComment, SpeciesFeedback, BapSubmission, SmpSubmission,
)
from species.asn_tools.text_normalize import normalize_species_text

NAME_FIELDS = ['name', 'alt_name', 'common_name']
FREE_TEXT_FIELDS = ['description', 'local_distribution']


def _recompute_cares_registration_name(reg):
    return f'{reg.species.name} - {reg.aquarist_name}' if reg.species_id else reg.name


def _recompute_bap_species_name(bs):
    return bs.species.name if bs.species_id else bs.name


def _recompute_species_comment_name(c):
    if c.user_id and c.species_id:
        return f'{c.user.get_display_name()} - {c.species.name}'
    return c.name


def _recompute_species_feedback_name(fb):
    if not fb.species_id:
        return fb.name
    if fb.user_id:
        identifier = fb.user.username
    elif fb.email:
        identifier = fb.email.split('@')[0]
    else:
        identifier = 'Anonymous'
    return f'{fb.species.name} - {identifier}'


def _recompute_submission_name(s):
    if s.aquarist_id and s.club_id and s.speciesInstance_id:
        return f'{s.aquarist.username} - {s.club.name} - {s.speciesInstance.name}'
    return s.name


# (model, recompute fn, related fields to select_related for efficiency)
LABEL_RECOMPUTERS = [
    (CaresRegistration, _recompute_cares_registration_name, ('species',)),
    (BapSpecies, _recompute_bap_species_name, ('species',)),
    (SpeciesComment, _recompute_species_comment_name, ('user', 'species')),
    (SpeciesFeedback, _recompute_species_feedback_name, ('user', 'species')),
    (BapSubmission, _recompute_submission_name, ('aquarist', 'club', 'speciesInstance')),
    (SmpSubmission, _recompute_submission_name, ('aquarist', 'club', 'speciesInstance')),
]


def refresh_labels(apply, writer):
    """
    Re-derive every label built from a (now-clean) Species/SpeciesInstance
    name and write it back if it differs - see PASS1_SCOPE.md section 2,
    "Labels built from species.name".
    """
    total = 0
    for model, recompute, related in LABEL_RECOMPUTERS:
        for obj in model.objects.select_related(*related).all():
            new_name = recompute(obj)
            if new_name != obj.name:
                writer.writerow([model.__name__, obj.pk, 'name', obj.name, new_name])
                total += 1
                if apply:
                    model.objects.filter(pk=obj.pk).update(name=new_name)
    return total


class Command(BaseCommand):
    help = (
        'Normalize quotes/whitespace in Species and SpeciesInstance text fields. '
        'Dry run by default; pass --apply to write the changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true', default=False,
            help='Write the changes. Default is a dry run (report only, nothing written).',
        )
        parser.add_argument(
            '--csv-log', default=None,
            help='Path for the CSV change log (default: normalize_species_text_<timestamp>.csv)',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        csv_path = options['csv_log'] or f'normalize_species_text_{datetime.now():%Y%m%d_%H%M%S}.csv'

        if apply:
            self.stdout.write(self.style.SUCCESS('APPLY MODE - changes will be written'))
        else:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be written (pass --apply to write them)'))

        with open(csv_path, 'w', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(['model', 'pk', 'field', 'before', 'after'])

            # Pass 1: normalize every Species.name (even unchanged ones) to
            # group collisions - two currently-still-dirty rows can both
            # normalize to the same clean name, so this has to compare
            # POST-normalization names, not raw current ones.
            all_species = list(Species.objects.all())
            name_groups = {}
            for sp in all_species:
                key = normalize_species_text(sp.name).lower()
                name_groups.setdefault(key, []).append(sp)
            collision_pks = {sp.pk for group in name_groups.values() if len(group) > 1 for sp in group}

            species_changes = []
            for sp in all_species:
                if sp.pk in collision_pks:
                    continue
                changes = {}
                for field in NAME_FIELDS:
                    before = getattr(sp, field) or ''
                    after = normalize_species_text(before)
                    if after != before:
                        changes[field] = (before, after)
                for field in FREE_TEXT_FIELDS:
                    before = getattr(sp, field) or ''
                    after = normalize_species_text(before, keep_linebreaks=True)
                    if after != before:
                        changes[field] = (before, after)
                if changes:
                    species_changes.append((sp, changes))
                    for field, (before, after) in changes.items():
                        writer.writerow(['Species', sp.pk, field, before, after])
                        self.stdout.write(f'Species pk={sp.pk} {field}: {before} -> {after}')

            instance_changes = []
            for si in SpeciesInstance.objects.all():
                before = si.name or ''
                after = normalize_species_text(before)
                if after != before:
                    instance_changes.append((si, after))
                    writer.writerow(['SpeciesInstance', si.pk, 'name', before, after])
                    self.stdout.write(f'SpeciesInstance pk={si.pk} name: {before} -> {after}')

            collisions = [group for group in name_groups.values() if len(group) > 1]
            if collisions:
                self.stdout.write(self.style.ERROR(f'\n{len(collisions)} collision(s) - NOT renamed automatically, merge by hand:'))
                for group in collisions:
                    key = normalize_species_text(group[0].name).lower()
                    names = ', '.join(f'pk={s.pk} "{s.name}"' for s in group)
                    self.stdout.write(self.style.ERROR(f'  {names}  (all normalize to "{key}")'))
                    writer.writerow(['Species', '/'.join(str(s.pk) for s in group), 'COLLISION', names, key])

            if not apply:
                self.stdout.write(self.style.WARNING(
                    f'\nDry run complete. {len(species_changes)} species field change(s), '
                    f'{len(instance_changes)} species-instance name change(s), '
                    f'{len(collisions)} collision(s). Change log: {csv_path}'
                ))
                return

            with transaction.atomic():
                for sp, changes in species_changes:
                    for field, (before, after) in changes.items():
                        setattr(sp, field, after)
                    sp.save()

                for si, after in instance_changes:
                    si.name = after
                    si.save()

                label_count = refresh_labels(apply=True, writer=writer)

            self.stdout.write(self.style.SUCCESS(
                f'\nApplied: {len(species_changes)} species field change(s), '
                f'{len(instance_changes)} species-instance name change(s), '
                f'{label_count} label refresh(es). '
                f'{len(collisions)} collision(s) left untouched - merge by hand. '
                f'Change log: {csv_path}'
            ))
