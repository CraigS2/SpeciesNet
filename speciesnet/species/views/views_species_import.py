"""
CARES Species Import – staging, review, and commit workflow views.
"""
import difflib
import re

from .base import *
from django.utils import timezone
from species.models import SpeciesImportStaging, SpeciesFeedback
from species.forms import SpeciesImportStagingForm
from species.asn_tools.asn_csv_tools import (import_csv_species_to_staging, commit_species_import_staging,
                                              import_csv_species_reference_links, _reference_link_url_for_cso_species,)


_WORD_TOKEN_RE = re.compile(r'\s+|\S+')


def _word_diff(old_text, new_text):
    """
    Word-level diff between *old_text* (ASN) and *new_text* (CSO) for the
    review screen's diff column (PASS2_SCOPE.md 4.3). Returns a list of
    {'tag': 'equal'|'delete'|'insert', 'text': str} tokens.
    """
    old_tokens = _WORD_TOKEN_RE.findall(old_text or '')
    new_tokens = _WORD_TOKEN_RE.findall(new_text or '')
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    result = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.append({'tag': 'equal', 'text': ''.join(old_tokens[i1:i2])})
        elif tag == 'delete':
            result.append({'tag': 'delete', 'text': ''.join(old_tokens[i1:i2])})
        elif tag == 'insert':
            result.append({'tag': 'insert', 'text': ''.join(new_tokens[j1:j2])})
        elif tag == 'replace':
            result.append({'tag': 'delete', 'text': ''.join(old_tokens[i1:i2])})
            result.append({'tag': 'insert', 'text': ''.join(new_tokens[j1:j2])})
    return result


# ---------------------------------------------------------------------------
# Step 1: Upload CSV and create staging records
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def importSpeciesToStaging(request):
    """Upload a CARES species CSV and parse it into staging records for review."""
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    form = ImportCsvForm()
    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save(commit=False)
            import_archive.aquarist = request.user
            import_archive.name = f"{request.user.username}_cares_species_staging"
            import_archive.save()

            summary = import_csv_species_to_staging(import_archive, request.user)
            logger.info(
                'User %s created CARES staging import %s: %s',
                request.user.username, import_archive.pk, summary,
            )
            messages.success(
                request,
                f"Staging import complete – {summary['new']} new, "
                f"{summary['update']} updates, {summary['conflict']} conflicts, "
                f"{summary['skip']} unchanged, {summary['error']} errors.",
            )
            return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[import_archive.pk]))
        
    context = {'form': form}
    return render(request, 'species/import/importSpeciesStaging.html', context)


# ---------------------------------------------------------------------------
# Step 2a: Review all staging records for an import archive
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def reviewSpeciesImport(request, pk):
    """Display all staging records for an ImportArchive with summary stats."""
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    import_archive = get_object_or_404(ImportArchive, pk=pk)
    staging_qs = SpeciesImportStaging.objects.filter(import_archive=import_archive).select_related('existing_species')

    # Filter by action type if requested
    action_filter = request.GET.get('action', '')
    status_filter = request.GET.get('status', '')
    if action_filter:
        staging_qs = staging_qs.filter(action=action_filter)
    if status_filter:
        staging_qs = staging_qs.filter(review_status=status_filter)

    # Django templates can't read a key starting with '_' (changed_fields'
    # internal '_committed_at' marker), so compute a plain flag here.
    staging_records = list(staging_qs)
    for record in staging_records:
        record.is_committed = bool((record.changed_fields or {}).get('_committed_at'))

    # Summary counts (always over the full set for the archive)
    all_staging = SpeciesImportStaging.objects.filter(import_archive=import_archive)
    all_rows = list(all_staging.only('review_status', 'changed_fields'))
    summary = {
        'new':      all_staging.filter(action=SpeciesImportStaging.ImportAction.NEW).count(),
        'update':   all_staging.filter(action=SpeciesImportStaging.ImportAction.UPDATE).count(),
        'conflict': all_staging.filter(action=SpeciesImportStaging.ImportAction.CONFLICT).count(),
        'skip':     all_staging.filter(action=SpeciesImportStaging.ImportAction.SKIP).count(),
        'pending':  all_staging.filter(review_status=SpeciesImportStaging.ReviewStatus.PENDING).count(),
        'approved': all_staging.filter(review_status__in=[
            SpeciesImportStaging.ReviewStatus.APPROVED,
            SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE,
        ]).count(),
        'rejected': all_staging.filter(review_status=SpeciesImportStaging.ReviewStatus.REJECTED).count(),
        'total':    all_staging.count(),
        'committed': sum(1 for r in all_rows if (r.changed_fields or {}).get('_committed_at')),
        'to_commit': sum(
            1 for r in all_rows
            if r.review_status in (
                SpeciesImportStaging.ReviewStatus.APPROVED,
                SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE,
            ) and not (r.changed_fields or {}).get('_committed_at')
        ),
    }

    context = {
        'import_archive': import_archive,
        'staging_records': staging_records,
        'summary': summary,
        'action_filter': action_filter,
        'status_filter': status_filter,
        'action_choices': SpeciesImportStaging.ImportAction.choices,
        'status_choices': SpeciesImportStaging.ReviewStatus.choices,
    }
    return render(request, 'species/import/reviewSpeciesImport.html', context)


# ---------------------------------------------------------------------------
# Step 2b: Review a single staging record (side-by-side comparison)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def reviewSpeciesImportDetail(request, staging_id):
    """Side-by-side comparison and approve/reject of an individual staging record."""
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    staging = get_object_or_404(SpeciesImportStaging, pk=staging_id)
    import_archive = staging.import_archive
    is_cso_sync = import_archive.source == ImportArchive.ImportSource.CSO_SYNC

    form = SpeciesImportStagingForm(instance=staging)
    if request.method == 'POST':
        form = SpeciesImportStagingForm(request.POST, instance=staging)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.reviewed_by = request.user
            updated.reviewed_at = timezone.now()
            updated.save()
            logger.info(
                'User %s set staging %s to %s',
                request.user.username, staging.pk, updated.review_status,
            )
            messages.success(request, f'Staging record updated to {updated.get_review_status_display()}.')
            return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[import_archive.pk]))

    # Build field comparison rows for the template - codes/facts only;
    # description/local_distribution get their own diff+edit section below.
    field_labels = {
        'name':                  'Scientific Name',
        'alt_name':              'Alternate Name',
        'common_name':           'Common Name',
        'category':              'Category',
        'global_region':         'Global Region',
        'cares_family':          'CARES Family',
        'cares_assessment_date': 'CARES Assessment Date',
        'cares_classification':  'CARES Classification',
        'iucn_red_list':         'IUCN Red List Status',
        'iucn_assessment_date':  'IUCN Assessment Date',
    }
    changed_fields = staging.changed_fields or {}
    comparison = []
    for field, label in field_labels.items():
        raw_current = getattr(staging.existing_species, field, None) if staging.existing_species else None
        current_val = str(raw_current) if raw_current is not None else ''
        raw_new = getattr(staging, f'new_{field}', None)
        new_val = str(raw_new) if raw_new is not None else ''
        entry = changed_fields.get(field, {})
        comparison.append({
            'field': field,
            'label': label,
            'current': current_val,
            'proposed': new_val,
            'changed': field in changed_fields,
            'auto': bool(entry.get('auto')),
            'invalid': bool(entry.get('invalid')),
        })

    # PASS2_SCOPE.md 4.3: description/local_distribution get ASN's text, CSO's
    # text, a word diff, and an editable "ASN final text" box (the form field).
    text_diffs = {}
    for field, label in (('description', 'Description'), ('local_distribution', 'Local Distribution')):
        current_val = getattr(staging.existing_species, field, '') if staging.existing_species else ''
        proposed_val = getattr(staging, f'new_{field}', '') or ''
        text_diffs[field] = {
            'label': label,
            'current': current_val or '',
            'proposed': proposed_val,
            'changed': field in changed_fields,
            'diff': _word_diff(current_val, proposed_val) if field in changed_fields else [],
        }

    feedback_list = []
    if staging.existing_species:
        feedback_list = list(
            SpeciesFeedback.objects.filter(species=staging.existing_species).order_by('-created')
        )

    # 'caresSpecies' only renders on Site2 (CSO) - this staging/review
    # workflow runs on Site1 (ASN), so the link to the species' own page
    # here must use 'species', not 'caresSpecies'.
    asn_species_url = (
        reverse('species', args=[staging.existing_species.pk]) if staging.existing_species else None
    )
    cso_species_url = _reference_link_url_for_cso_species(changed_fields.get('_cso_species_id')) if is_cso_sync else None

    auto_changes = [
        {'field': field, **entry} for field, entry in changed_fields.items()
        if not field.startswith('_') and entry.get('auto')
    ]

    context = {
        'staging': staging,
        'import_archive': import_archive,
        'is_cso_sync': is_cso_sync,
        'form': form,
        'comparison': comparison,
        'text_diffs': text_diffs,
        'auto_changes': auto_changes,
        'feedback_list': feedback_list,
        'asn_species_url': asn_species_url,
        'cso_species_url': cso_species_url,
    }
    return render(request, 'species/import/reviewSpeciesImportDetail.html', context)


# ---------------------------------------------------------------------------
# Step 3a: Bulk approve
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def approveSpeciesImportBatch(request, pk):
    """Bulk-approve all PENDING staging records for an ImportArchive."""
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    import_archive = get_object_or_404(ImportArchive, pk=pk)
    if request.method == 'POST':
        action_filter = request.POST.get('action_filter', '')
        qs = SpeciesImportStaging.objects.filter(
            import_archive=import_archive,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )
        if action_filter:
            qs = qs.filter(action=action_filter)

        if import_archive.source == ImportArchive.ImportSource.CSO_SYNC:
            # D6: bulk approve only for rows with automatic changes alone.
            # Rows with only_auto changes are already auto-approved when the
            # batch is built, so this should normally match nothing - it's
            # a defensive guard, not the usual path. Anything with a real
            # text decision pending must go through "Keep ASN text" (below)
            # or the per-record review screen.
            ids = [
                row.pk for row in qs.only('pk', 'changed_fields')
                if all(
                    entry.get('auto') for key, entry in (row.changed_fields or {}).items()
                    if not key.startswith('_')
                )
            ]
            qs = SpeciesImportStaging.objects.filter(pk__in=ids)

        count = qs.update(
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        logger.info('User %s bulk-approved %d staging records for archive %s', request.user.username, count, pk)
        messages.success(request, f'{count} staging record(s) approved.')

    return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[pk]))


# ---------------------------------------------------------------------------
# Step 3c: Bulk "keep ASN text" (D6) - marks rows reviewed without touching
# final_description/final_local_distribution, which default to ASN's
# current text. Safe for text-decision rows, unlike plain bulk-approve.
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def keepAsnTextSpeciesImportBatch(request, pk):
    """Bulk-approve PENDING UPDATE staging records, keeping each one's
    pre-filled ASN text.

    PASS3_SCOPE.md Fix 6: CSO_SYNC only, and UPDATE rows only. NEW rows must
    never be bulk-approved this way - final_description/final_local_distribution
    start blank for a NEW row (4.6), so bulk-approving one would commit a
    species with no text at all. A CSV batch has no "ASN text" concept
    (final_* isn't used on the CSV commit path), so it's refused outright.
    """
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    import_archive = get_object_or_404(ImportArchive, pk=pk)
    if request.method == 'POST':
        if import_archive.source != ImportArchive.ImportSource.CSO_SYNC:
            messages.error(request, "Keep ASN Text only applies to CSO sync batches.")
            return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[pk]))

        action_filter = request.POST.get('action_filter', '')
        qs = SpeciesImportStaging.objects.filter(
            import_archive=import_archive,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
            action=SpeciesImportStaging.ImportAction.UPDATE,
        )
        if action_filter and action_filter != SpeciesImportStaging.ImportAction.UPDATE:
            qs = SpeciesImportStaging.objects.none()
        count = qs.update(
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        logger.info('User %s bulk-kept-ASN-text for %d staging records in archive %s', request.user.username, count, pk)
        messages.success(request, f"{count} staging record(s) approved, keeping ASN's current text. NEW rows are never affected by this action.")

    return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[pk]))


# ---------------------------------------------------------------------------
# Step 3b: Bulk reject
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def rejectSpeciesImportBatch(request, pk):
    """Bulk-reject all PENDING staging records for an ImportArchive."""
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    import_archive = get_object_or_404(ImportArchive, pk=pk)
    if request.method == 'POST':
        action_filter = request.POST.get('action_filter', '')
        qs = SpeciesImportStaging.objects.filter(
            import_archive=import_archive,
            review_status=SpeciesImportStaging.ReviewStatus.PENDING,
        )
        if action_filter:
            qs = qs.filter(action=action_filter)
        count = qs.update(
            review_status=SpeciesImportStaging.ReviewStatus.REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        logger.info('User %s bulk-rejected %d staging records for archive %s', request.user.username, count, pk)
        messages.success(request, f'{count} staging record(s) rejected.')

    return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[pk]))


# ---------------------------------------------------------------------------
# Step 4: Commit all approved staging records
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def commitSpeciesImport(request, pk):
    """Commit all APPROVED staging records to the Species table."""
    if not user_can_review_species_import(request.user):
        raise PermissionDenied()

    import_archive = get_object_or_404(ImportArchive, pk=pk)
    # Same staleness fix as the review list's "to_commit" count: a row
    # already committed on an earlier run must not inflate this number -
    # otherwise this confirmation page would say "commit N records" right
    # after the list page correctly said there were none left.
    approved_count = sum(
        1 for r in SpeciesImportStaging.objects.filter(
            import_archive=import_archive,
            review_status__in=[
                SpeciesImportStaging.ReviewStatus.APPROVED,
                SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE,
            ],
        ).only('changed_fields')
        if not (r.changed_fields or {}).get('_committed_at')
    )

    if request.method == 'POST':
        results = commit_species_import_staging(import_archive, request.user)
        logger.info(
            'User %s committed CARES import archive %s: %s',
            request.user.username, pk, results,
        )
        context = {
            'import_archive': import_archive,
            'results': results,
        }
        return render(request, 'species/import/commitSpeciesImportResults.html', context)

    # GET: show confirmation page
    context = {
        'import_archive': import_archive,
        'approved_count': approved_count,
    }
    return render(request, 'species/import/commitSpeciesImportConfirm.html', context)


# ---------------------------------------------------------------------------
# Species Reference Link CSV Import
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def importSpeciesReferenceLinks(request):
    """Upload a CSV file and import SpeciesReferenceLink objects row by row.

    Expected CSV columns: species, reference_url, name_prefix
    """
    if not user_is_admin(request.user):
        raise PermissionDenied()

    form = ImportCsvForm()
    summary = None

    if request.method == 'POST':
        form = ImportCsvForm(request.POST, request.FILES)
        if form.is_valid():
            import_archive = form.save(commit=False)
            import_archive.aquarist = request.user
            import_archive.name = f"{request.user.username}_species_reference_link_import"
            import_archive.save()

            summary = import_csv_species_reference_links(import_archive, request.user)

            logger.info(
                'User %s completed species reference link import %s: %d succeeded, %d errors',
                request.user.username,
                import_archive.pk,
                summary['success_count'],
                summary['error_count'],
            )
            return HttpResponseRedirect(reverse("importArchiveResults", args=[import_archive.id]))

    context = {
        'form': form,
        'summary': summary,
    }
    return render(request, 'species/import/importSpeciesReferenceLinks.html', context)
