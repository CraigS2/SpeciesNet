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
    return _FILTER_QUERY_STRINGS.get(value, '?filter=all')


### Submit Species Feedback (accessible to all users, anonymous and logged-in)

def submitSpeciesFeedback(request, pk):
    species = get_object_or_404(Species, pk=pk)
    print ('Requesting User Feedback for species: ' + species.name)

    if request.method == 'POST':
        register_heif_opener()

        # print ('Processing User Feedback ... ')
        # post_data = request.POST.copy()  # Make a mutable copy
        # if request.user.is_authenticated:
        #     post_data['user'] = request.user.id  # Set the user ID in form data
        #     post_data['email'] = ''

        form = SpeciesFeedbackForm(request.POST, request.FILES, user=request.user)
        if request.user.is_authenticated:
            form.instance.user = request.user
            form.instance.email = ''
            print(f'Authenticated user: {request.user.username} - set user on form instance')

        if form.is_valid():
            try:
                feedback = form.save(commit=False)
                feedback.species = species

                print ('Feedback form submitted and validated for species: ' + species.name)

                if request.user.is_authenticated:
                    feedback.user = request.user
                    feedback.email = ''
                    print(f'Set feedback.user to: {request.user.username}')
                else:
                    feedback.user = None
                    print(f'Anonymous submission with email: {feedback.email}')

                print(f'Before full_clean - user: {feedback.user}, email: "{feedback.email}"')
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
                print('='*50)
                print('Feedback form validation failure (from full_clean):')
                print('ValidationError object:', e)
                print('='*50)
                
                # Handle both dict-style and list-style validation errors
                if hasattr(e, 'message_dict'):
                    for field, errors in e.message_dict.items():
                        print(f'Field "{field}": {errors}')
                        for error in errors:
                            messages.error(request, f'{field}: {error}' if field != '__all__' else error)
                else:
                    print(f'General errors: {e.messages}')
                    for error in e.messages:
                        messages.error(request, error)
                        
            # except IntegrityError:
            #     messages.error(request, 'You have already submitted feedback for species %s', species.name)
            #     logger.warning('Duplicate feedback submission blocked for species %s', species.name)
        else:
            print('='*50)
            print('Form data fails validation!')
            print('Form errors:', form.errors)
            print('Form errors as JSON:', form.errors.as_json())
            print('='*50)
            
            # Add each field error to messages
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, error)
                    else:
                        print(f'Field "{field}" error: {error}')
                        messages.error(request, f'{field}: {error}')
            
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

# @login_required(login_url='login')
# def approveSpeciesFeedback(request, pk):
#     if not request.user.is_staff:
#         raise PermissionDenied()

#     feedback = get_object_or_404(SpeciesFeedback, pk=pk)

#     if request.method == 'POST':
#         feedback.approved = True
#         feedback.reviewed_by = request.user
#         feedback.reviewed_at = timezone.now()
#         feedback.save()
#         logger.info('Staff user %s approved feedback %s for species: %s', request.user.username, pk, feedback.species.name)
#         messages.success(request, f'Feedback from "{feedback.name}" has been approved.')

#     filter_query = _safe_filter_query(request.GET.get('filter', 'all'))
#     return redirect(reverse('speciesFeedbackTools') + filter_query)

### Apply Species Feedback Photo to Species Profile (staff-only)

@login_required(login_url='login')
def applySpeciesFeedbackPhoto(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied()
    
    feedback = get_object_or_404(SpeciesFeedback, pk=pk)
    
    if request.method == 'POST':
        if feedback.species_image:
            # Apply the photo to the species
            species = feedback.species
            species.species_image = feedback.species_image
            if feedback.species_photo_credit:
                species.photo_credit = feedback.species_photo_credit
            species.last_edited_by = request.user
            species.save()
            
            # Mark feedback as approved
            feedback.approved = True
            feedback.reviewed_by = request.user
            feedback.reviewed_at = timezone.now()
            feedback.save()
            
            logger.info('Staff user %s applied photo from feedback %s to species: %s', 
                       request.user.username, pk, feedback.species.name)
            messages.success(request, f'Photo from "{feedback.name}" has been applied to {species.name}.')
        else:
            messages.error(request, 'No photo attached to this feedback.')
    
    filter_query = _safe_filter_query(request.GET.get('filter', 'all'))
    return redirect(reverse('speciesFeedbackTools') + filter_query)


### Archive Species Feedback (staff-only)

@login_required(login_url='login')
def archiveSpeciesFeedback(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied()
    
    feedback = get_object_or_404(SpeciesFeedback, pk=pk)
    
    if request.method == 'POST':
        feedback.approved = True
        feedback.reviewed_by = request.user
        feedback.reviewed_at = timezone.now()
        feedback.save()
        logger.info('Staff user %s archived feedback %s for species: %s', 
                   request.user.username, pk, feedback.species.name)
        messages.success(request, f'Feedback from "{feedback.name}" has been archived.')
    
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
