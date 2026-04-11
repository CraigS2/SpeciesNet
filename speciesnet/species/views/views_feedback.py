"""
Species Feedback views: submission form, staff tools, approve and delete actions
"""

from .base import *
from species.models import SpeciesFeedback
from species.forms import SpeciesFeedbackForm
from django.core.paginator import Paginator


VALID_FILTER_VALUES = {'all', 'pending', 'approved'}

# Mapping from validated filter values to hardcoded query strings (prevents URL injection)
_FILTER_QUERY_STRINGS = {
    'all': '?filter=all',
    'pending': '?filter=pending',
    'approved': '?filter=approved',
}


def _safe_filter_query(value):
    """Return a hardcoded query string for a validated filter value."""
    return _FILTER_QUERY_STRINGS.get(value, '?filter=all') if value in VALID_FILTER_VALUES else '?filter=all'


### Submit Species Feedback (accessible to all users, anonymous and logged-in)

def submitSpeciesFeedback(request, pk):
    species = get_object_or_404(Species, pk=pk)

    if request.method == 'POST':
        register_heif_opener()
        form = SpeciesFeedbackForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                feedback = form.save(commit=False)
                feedback.species = species

                if request.user.is_authenticated:
                    feedback.user = request.user
                    feedback.email = ''
                else:
                    feedback.user = None

                feedback.full_clean()
                feedback.save()

                if feedback.species_image:
                    processUploadedImageFile(feedback.species_image, feedback.name, request)

                if request.user.is_authenticated:
                    logger.info('User %s submitted feedback for species: %s', request.user.username, species.name)
                else:
                    logger.info('Anonymous user (%s) submitted feedback for species: %s', feedback.email, species.name)

                messages.success(request, 'Thank you! Your feedback has been submitted and will be reviewed by our staff.')

                # Redirect to appropriate species page
                if species.render_cares:
                    return redirect('caresSpecies', pk=species.id)
                return redirect('species', pk=species.id)

            except ValidationError as e:
                for field, errors in e.message_dict.items() if hasattr(e, 'message_dict') else [('__all__', e.messages)]:
                    for error in errors:
                        messages.error(request, error)
            except IntegrityError:
                messages.error(request, 'You have already submitted feedback for this species.')
                logger.warning('Duplicate feedback submission blocked for species %s', species.name)
        else:
            messages.error(request, 'Please correct the errors highlighted below.')
    else:
        form = SpeciesFeedbackForm(user=request.user)

    context = {
        'species': species,
        'form': form,
    }
    return render(request, 'species/speciesFeedbackForm.html', context)


### Species Feedback Tools (staff-only)

@login_required(login_url='login')
def speciesFeedbackTools(request):
    if not request.user.is_staff:
        raise PermissionDenied()

    raw_filter = request.GET.get('filter', 'all')
    display_filter = raw_filter if raw_filter in VALID_FILTER_VALUES else 'all'
    feedback_qs = SpeciesFeedback.objects.select_related('species', 'user', 'reviewed_by').all()

    if display_filter == 'pending':
        feedback_qs = feedback_qs.filter(approved=False)
    elif display_filter == 'approved':
        feedback_qs = feedback_qs.filter(approved=True)

    paginator = Paginator(feedback_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    logger.info('Staff user %s visited speciesFeedbackTools page (filter=%s)', request.user.username, display_filter)

    context = {
        'page_obj': page_obj,
        'filter_status': display_filter,
    }
    return render(request, 'species/tools/speciesFeedbackTools.html', context)


### Approve Species Feedback (staff-only)

@login_required(login_url='login')
def approveSpeciesFeedback(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied()

    feedback = get_object_or_404(SpeciesFeedback, pk=pk)

    if request.method == 'POST':
        feedback.approved = True
        feedback.reviewed_by = request.user
        feedback.reviewed_at = timezone.now()
        feedback.save()
        logger.info('Staff user %s approved feedback %s for species: %s', request.user.username, pk, feedback.species.name)
        messages.success(request, f'Feedback from "{feedback.name}" has been approved.')

    filter_query = _safe_filter_query(request.GET.get('filter', 'all'))
    return redirect(reverse('speciesFeedbackTools') + filter_query)


### Delete Species Feedback (staff-only)

@login_required(login_url='login')
def deleteSpeciesFeedback(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied()

    feedback = get_object_or_404(SpeciesFeedback, pk=pk)

    if request.method == 'POST':
        species_name = feedback.species.name
        feedback_name = feedback.name
        feedback.delete()
        logger.info('Staff user %s deleted feedback "%s" for species: %s', request.user.username, feedback_name, species_name)
        messages.success(request, f'Feedback "{feedback_name}" has been deleted.')
        filter_query = _safe_filter_query(request.POST.get('filter', 'all'))
        return redirect(reverse('speciesFeedbackTools') + filter_query)

    raw_filter = request.GET.get('filter', 'all')
    filter_status = raw_filter if raw_filter in VALID_FILTER_VALUES else 'all'
    context = {
        'feedback': feedback,
        'filter_status': filter_status,
    }
    return render(request, 'species/tools/deleteSpeciesFeedback.html', context)
