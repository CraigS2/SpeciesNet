"""
User-related views: profiles, authentication, email communication, aquarist directory
"""

## TODO Review ALL  if request.method == 'POST': statements and confirm/add else to handle validation feedback to user if bad data entered

from .base import *

### User Profile

@login_required(login_url='login')
def userProfile(request):
    aquarist = request.user
    context = {'aquarist': aquarist}
    logger.info('User %s visited their profile page', request.user.username)
    return render(request, 'species/userProfile.html', context)


@login_required(login_url='login')
def editUserProfile(request):
    cur_user = request.user

    if request.method == 'POST':
        form = UserProfileForm2(request.POST, instance=cur_user)
        if form.is_valid():
            # handling social urls outside normal validation to cleanly map 3 cases
            # instagram, facebook, and youtube each have unique validation routines based on url domain 
            cur_user = form.save(commit=False)
            url_validation_failed = False
            if cur_user.instagram_url:
                valid_url = validate_normalize_instagram_url(cur_user.instagram_url)
                if not valid_url:
                    form.add_error('instagram_url', 'Please enter a valid Instagram URL')
                    url_validation_failed = True
                else:
                    cur_user.instagram_url = valid_url 
            if cur_user.facebook_url:
                valid_url = validate_normalize_facebook_url(cur_user.facebook_url)
                if not valid_url:
                    form.add_error('facebook_url', 'Please enter a valid Facebook URL')
                    url_validation_failed = True
                else:
                    cur_user.facebook_url = valid_url
            if cur_user.youtube_url:
                valid_url = validate_normalize_youtube_url(cur_user.youtube_url)
                if not valid_url:
                    form.add_error('youtube_url', 'Please enter a valid YouTube URL')
                    url_validation_failed = True
                else:
                    cur_user.youtube_url = valid_url
            if not url_validation_failed:
                cur_user.save()
                logger.info('User %s edited their profile page', request.user.username)
                messages.success(request, 'User profile updated successfully!')
                context = {'aquarist': request.user}
                return render(request, 'species/userProfile.html', context)
        
        if not form.is_valid() or url_validation_failed:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UserProfileForm2(instance=cur_user)

    context = {'form': form, 'user': request.user}
    return render(request, 'species/editUserProfile.html', context)


### View Aquarist Profile (with Tile/List Toggle)

def aquarist(request, pk):
    """
    Display an aquarist's fishroom with species they keep.
    Supports both tile and list views via ?view=tile or ?view=list query parameter.
    """
    aquarist = User.objects.get(id=pk)
    userCanEdit = user_can_edit_a(request.user, aquarist)

    view_type = 'tile'
    view_choice = request.GET.get('view')
    if view_choice in ['tile', 'list']:
        view_type = view_choice            # toggle tile/view selected on page
    elif request.user.is_authenticated and not request.user.prefer_tile_view:
        view_type = 'list'                 # user has list as view preference

    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).select_related('species').order_by('species__name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=False).select_related('species').order_by('species__name')
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist page for %s.', request.user.username, aquarist.username)
    else:
        logger.info('Anonymous user visited aquarist page for %s.', aquarist.username)
    context = {
        'aquarist': aquarist,
        'speciesKept': speciesKept,
        'speciesPreviouslyKept': speciesPreviouslyKept,
        'userCanEdit': userCanEdit,
        'current_view': view_type,  # Pass view type to template for button state
    }
    if view_type == 'tile':
        template = 'species/aquarist1.html'  # Tile view template
    else:
        template = 'species/aquarist2.html'   # List view template
    return render(request, template, context)

### Aquarists Directory

class AquaristListView(ListView):
    model = User
    template_name = "species/aquarists.html"
    context_object_name = "aquarist_list"
    paginate_by = 100

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = User.objects.all()
        query_text = self.request.GET.get('q', '')
        if query_text: 
            queryset = queryset.filter(
                Q(username__icontains=query_text) |
                Q(first_name__icontains=query_text) |
                Q(last_name__icontains=query_text)
            )
            queryset = queryset.exclude(is_private_name=True)
        return queryset

    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated:
            logger.info('User %s visited aquarists page.', self.request.user.username)
        else:
            logger.info('Anonymous user visited aquarists page.')
        context = super().get_context_data(**kwargs)
        context['query_text'] = self.request.GET.get('q', '')
        context['recent_speciesInstances'] = SpeciesInstance.objects.all()[:36]
        return context


### Email Aquarist

def emailAquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    cur_user = request.user
    form = EmailAquaristForm()
    context = {'form':  form, 'aquarist':  aquarist}
    
    if request.method == 'POST':
        form2 = EmailAquaristForm(request.POST)
        mailed_msg = f"Your email to {aquarist.username} has been sent."
        mailed = False
        
        if form2.is_valid():
            email = form2.save(commit=False)
            email.name = f"{cur_user.username} to {aquarist.username}"
            email.send_to = aquarist
            email.send_from = cur_user
            private_message = aquarist.is_private_email
            
            if not email.email_subject:
                email.email_subject = f"AquaristSpecies.net: {cur_user.username} inquiry"
            else: 
                email.email_subject = f"AquaristSpecies.net: {cur_user.username} - {email.email_subject}"
            
            if not private_message:
                email.email_text = (
                    f"{email.email_text}\n\nMessage sent from {cur_user.username} (with email cc) to "
                    f"{aquarist.username} via AquaristSpecies.net."
                )
                email_message = EmailMessage(
                    email.email_subject,
                    email.email_text,
                    email.send_from.email,
                    [email.send_to.email],
                    bcc=['aquaristspecies@gmail.com'],
                    cc=[email.send_from.email]
                )
            else:
                email.email_text = (
                    f"{email.email_text}\n\nMessage sent from {cur_user.username} to {aquarist.username} "
                    f"via AquaristSpecies.net.\n\n"
                    f"IMPORTANT: Your AquaristSpecies.net profile is configured for private email."
                    f"To reply to {cur_user.username} use {cur_user.email}"
                )
                email_message = EmailMessage(
                    email.email_subject,
                    email.email_text,
                    email.send_from.email,
                    [email.send_to.email],
                    bcc=['aquaristspecies@gmail.com']
                )
            
            email.save()
            
            try: 
                email_message.send(fail_silently=False)
                mailed = True
                logger.info('User %s sent email to %s', request.user.username, aquarist.username)
            except SMTPException as e:
                mailed_msg = f"An error occurred sending your email to {aquarist.username}.SMTP Exception: {str(e)}"
                logger.error('User %s email failed to send to %s: SMTPException %s', request.user.username, aquarist.username, str(e))
            except Exception as e:
                mailed_msg = f"An error occurred sending your email to {aquarist.username}.Exception: {str(e)}"
                logger.error('User %s email failed to send to %s: %s', request.user.username, aquarist.username, str(e))
        
        if not mailed:
            messages.error(request, mailed_msg)
        else:
            messages.success(request, mailed_msg)
        return HttpResponseRedirect(reverse("aquarist", args=[aquarist.id]))
    
    return render(request, 'species/emailAquarist.html', context)


### Login and Logout

def loginUser(request):
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            user = User.objects.get(email=email)
        except: 
            messages.error(request, 'Login failed - user not found')

        user = authenticate(request, email=email, password=password)
        if user is not None: 
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'User Email or Password does not exist')

    context = {'page':  page}
    return render(request, 'species/login_register.html', context)


def logoutUser(request):
    page = 'logout'
    logout(request)
    return redirect('home')


### Export Aquarists

@login_required(login_url='login')
def exportAquarists(request):
    return export_csv_aquarists()