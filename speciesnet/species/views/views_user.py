"""
User-related views: profiles, authentication, email communication, aquarist directory
"""

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
    form = UserProfileForm(instance=cur_user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=cur_user)
        if form.is_valid:
            form.save(commit=False)
            cur_user.first_name = form.instance.first_name
            cur_user.last_name = form.instance.last_name
            cur_user.state = form.instance.state
            cur_user.country = form.instance.country
            cur_user.is_private_name = form.instance.is_private_name
            cur_user.is_private_email = form.instance.is_private_email
            cur_user.is_private_location = form.instance.is_private_location
            cur_user.save()
            logger.info('User %s edited their profile page', request.user.username)
        else:
            error_msg = "Error saving User Profile changes"
            messages.error(request, error_msg)
        context = {'aquarist':  request.user}
        return render(request, 'species/userProfile.html', context)
    context = {'form': form}
    return render(request, 'species/editUserProfile.html', context)


### View Aquarist Profile

def aquarist(request, pk):
    aquarist = User.objects.get(id=pk)
    userCanEdit = user_can_edit_a(request.user, aquarist)
    speciesKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=True).order_by('name')
    speciesPreviouslyKept = SpeciesInstance.objects.filter(user=aquarist, currently_keep=False).order_by('name')
    speciesComments = SpeciesComment.objects.filter(user=aquarist)
    if request.user.is_authenticated:
        logger.info('User %s visited aquarist page for %s. ', request.user.username, aquarist.username)
    else:
        logger.info('Anonymous user visited aquarist page for %s.', aquarist.username)
    context = {
        'aquarist': aquarist,
        'speciesKept': speciesKept,
        'speciesPreviouslyKept': speciesPreviouslyKept,
        'speciesComments':  speciesComments,
        'userCanEdit': userCanEdit
    }
    return render(request, 'species/aquarist.html', context)


### Aquarists Directory

class AquaristListView(ListView):
    model = User
    template_name = "species/aquarists.html"
    context_object_name = "aquarist_list"
    paginate_by = 200

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