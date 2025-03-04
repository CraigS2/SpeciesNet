from django.urls import path, re_path
from django.conf.urls.static import static
from django.views.static import serve
#from django.conf.urls import url - deprecated
from django.conf import settings
from . import views

urlpatterns = [
    path('login/', views.loginUser, name="login"),
    path('logout/', views.logoutUser, name="logout"), 
    #path('register/', views.registerUser, name="register"), 

    path('', views.home, name="home"),

    path('aquarists/', views.aquarists, name="aquarists"),
    path('aquarist/<str:pk>/', views.aquarist, name="aquarist"),
    path('emailAquarist/<str:pk>/', views.emailAquarist, name="emailAquarist"),
    path('userProfile/', views.userProfile, name="userProfile"),
    path('editUserProfile/', views.editUserProfile, name="editUserProfile"),
    path('exportAquarists/', views.exportAquarists, name="exportAquarists"),

    path('species/<str:pk>/', views.species, name="species"), 
    path('createSpecies/', views.createSpecies, name="createSpecies"),
    path('editSpecies/<str:pk>/', views.editSpecies, name="editSpecies"),
    path('speciesComments/', views.speciesComments, name="speciesComments"),
    path('deleteSpecies/<str:pk>/', views.deleteSpecies, name="deleteSpecies"),
    path('deleteSpeciesComment/<str:pk>/', views.deleteSpeciesComment, name="deleteSpeciesComment"),    
    path('searchSpecies/', views.searchSpecies, name="searchSpecies"),
    path('exportSpecies/', views.exportSpecies, name="exportSpecies"),
    path('importSpecies/', views.importSpecies, name="importSpecies"),

    path('speciesInstance/<str:pk>/', views.speciesInstance, name="speciesInstance"), 
    path('createSpeciesInstance/<str:pk>/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('editSpeciesInstance/<str:pk>/', views.editSpeciesInstance, name="editSpeciesInstance"),
    path('deleteSpeciesInstance/<str:pk>/', views.deleteSpeciesInstance, name="deleteSpeciesInstance"), 
    path('exportSpeciesInstances/', views.exportSpeciesInstances, name="exportSpeciesInstances"),
    path('importSpeciesInstances/', views.importSpeciesInstances, name="importSpeciesInstances"),

    path('addSpeciesInstanceWizard1/', views.addSpeciesInstanceWizard1, name="addSpeciesInstanceWizard1"),
    path('addSpeciesInstanceWizard2/', views.addSpeciesInstanceWizard2, name="addSpeciesInstanceWizard2"),
    
    path('about_us/', views.about_us, name="about_us"),
    path('howItWorks/', views.howItWorks, name="howItWorks"),
    path('tools/', views.tools, name="tools"),
    path('working/', views.working, name="working"),

    path('importArchiveResults/<str:pk>/', views.importArchiveResults, name="importArchiveResults"),

    # re_path configuration for media files solves production error with nginx serving up image files
    re_path(r'^media/(?P<path>.*)$', serve,{'document_root': settings.MEDIA_ROOT}),
]

# extend urlpatterns to support Media images uploaded by user - development DEBUG environment
urlpatterns = urlpatterns + static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT)

