"""
CARES Species Import – staging, review, and commit workflow views.
"""

from .base import *
from django.utils import timezone
from species.models import SpeciesImportStaging
from species.forms import SpeciesImportStagingForm
from species.asn_tools.asn_csv_tools import (import_csv_species_to_staging, commit_species_import_staging,)


# ---------------------------------------------------------------------------
# Step 1: Upload CSV and create staging records
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def importSpeciesToStaging(request):
    """Upload a CARES species CSV and parse it into staging records for review."""
    if not user_is_admin(request.user):
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
    if not user_is_admin(request.user):
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

    # Summary counts (always over the full set for the archive)
    all_staging = SpeciesImportStaging.objects.filter(import_archive=import_archive)
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
    }

    context = {
        'import_archive': import_archive,
        'staging_records': staging_qs,
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
    if not user_is_admin(request.user):
        raise PermissionDenied()

    staging = get_object_or_404(SpeciesImportStaging, pk=staging_id)
    import_archive = staging.import_archive

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

    # Build field comparison rows for the template
    field_labels = {
        'name':                  'Scientific Name',
        'alt_name':              'Alternate Name',
        'common_name':           'Common Name',
        'description':           'Description',
        'category':              'Category',
        'global_region':         'Global Region',
        'local_distribution':    'Local Distribution',
        'cares_family':          'CARES Family',
        'cares_assessment_date': 'CARES Assessment Date',        
        'cares_classification':  'CARES Classification',
        'iucn_red_list':         'IUCN Red List Status',
        'iucn_assessment_date':  'IUCN Assessment Date',
    }
    comparison = []
    for field, label in field_labels.items():
        raw_current = getattr(staging.existing_species, field, None) if staging.existing_species else None
        current_val = str(raw_current) if raw_current is not None else ''
        raw_new = getattr(staging, f'new_{field}', None)
        new_val = str(raw_new) if raw_new is not None else ''
        changed = current_val != new_val
        comparison.append({
            'field': field,
            'label': label,
            'current': current_val,
            'proposed': new_val,
            'changed': changed,
        })

    context = {
        'staging': staging,
        'import_archive': import_archive,
        'form': form,
        'comparison': comparison,
    }
    return render(request, 'species/import/reviewSpeciesImportDetail.html', context)


# ---------------------------------------------------------------------------
# Step 3a: Bulk approve
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def approveSpeciesImportBatch(request, pk):
    """Bulk-approve all PENDING staging records for an ImportArchive."""
    if not user_is_admin(request.user):
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
            review_status=SpeciesImportStaging.ReviewStatus.APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        logger.info('User %s bulk-approved %d staging records for archive %s', request.user.username, count, pk)
        messages.success(request, f'{count} staging record(s) approved.')

    #return HttpResponseRedirect(reverse('species/import/reviewSpeciesImport', args=[pk]))
    return HttpResponseRedirect(reverse('reviewSpeciesImport', args=[pk]))


# ---------------------------------------------------------------------------
# Step 3b: Bulk reject
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def rejectSpeciesImportBatch(request, pk):
    """Bulk-reject all PENDING staging records for an ImportArchive."""
    if not user_is_admin(request.user):
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

    return HttpResponseRedirect(reverse('species/import/reviewSpeciesImport', args=[pk]))


# ---------------------------------------------------------------------------
# Step 4: Commit all approved staging records
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def commitSpeciesImport(request, pk):
    """Commit all APPROVED staging records to the Species table."""
    if not user_is_admin(request.user):
        raise PermissionDenied()

    import_archive = get_object_or_404(ImportArchive, pk=pk)
    approved_count = SpeciesImportStaging.objects.filter(
        import_archive=import_archive,
        review_status__in=[
            SpeciesImportStaging.ReviewStatus.APPROVED,
            SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE,
        ],
    ).count()

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
