from django.urls import path, re_path
from django.conf.urls.static import static
from django.views.static import serve
#from django.conf.urls import url - deprecated
from django.conf import settings
from . import views
from species.views import SpeciesListView



urlpatterns = [
    path('login/', views.loginUser, name="login"),
    path('logout/', views.logoutUser, name="logout"), 
    #path('register/', views.registerUser, name="register"), 

    path('', views.home, name="home"),

    path('userProfile/', views.userProfile, name="userProfile"),
    path('editUserProfile/', views.editUserProfile, name="editUserProfile"),

    path('aquarists/', views.AquaristListView.as_view(), name="aquarists"),

    path('aquarists2/', views.aquarists2, name="aquarists2"),
    path('aquarist/<str:pk>/', views.aquarist, name="aquarist"),
    path('emailAquarist/<str:pk>/', views.emailAquarist, name="emailAquarist"),
    path('exportAquarists/', views.exportAquarists, name="exportAquarists"),

    path('aquaristClubs/', views.aquaristClubs, name="aquaristClubs"),
    path('aquaristClub/<str:pk>/', views.aquaristClub, name="aquaristClub"), 
    path('aquaristClubMembers/<str:pk>/', views.aquaristClubMembers, name="aquaristClubMembers"), 
    path('aquaristClubMember/<str:pk>/', views.aquaristClubMember, name="aquaristClubMember"), 
    path('createAquaristClub/', views.createAquaristClub, name="createAquaristClub"),
    path('createAquaristClubMember/<str:pk>', views.createAquaristClubMember, name="createAquaristClubMember"),
    path('editAquaristClub/<str:pk>/', views.editAquaristClub, name="editAquaristClub"),
    path('editAquaristClubMember/<str:pk>/', views.editAquaristClubMember, name="editAquaristClubMember"),
    path('deleteAquaristClub/<str:pk>/', views.deleteAquaristClub, name="deleteAquaristClub"), 
    path('deleteAquaristClubMember/<str:pk>/', views.deleteAquaristClubMember, name="deleteAquaristClubMember"), 

    path('caresAdmin/', views.caresAdmin, name="caresAdmin"),
    #path('caresSpecies/', views.caresSpecies, name="caresSpecies"),
    path('caresSpeciesSearch/', views.CaresSpeciesListView.as_view(), name="caresSpeciesSearch"),
    path('caresRegistrations/', views.CaresRegistrationsView.as_view(), name="caresRegistrations"),
    path('caresRegistration/<str:pk>/', views.caresRegistration, name="caresRegistration"),
    path('createCaresRegistration/<str:pk>/', views.createCaresRegistration, name="createCaresRegistration"),
    path('editCaresRegistration/<str:pk>/', views.editCaresRegistration, name="editCaresRegistration"),
    path('deleteCaresRegistration/<str:pk>/', views.deleteCaresRegistration, name="deleteCaresRegistration"),

    path('species/<str:pk>/', views.species, name="species"), 
    path('createSpecies/', views.createSpecies, name="createSpecies"),
    path('editSpecies/<str:pk>/', views.editSpecies, name="editSpecies"),
    path('deleteSpecies/<str:pk>/', views.deleteSpecies, name="deleteSpecies"),
    path('speciesComments/', views.speciesComments, name="speciesComments"),
    path('editSpeciesComment/<str:pk>/', views.editSpeciesComment, name="editSpeciesComment"), 
    path('deleteSpeciesComment/<str:pk>/', views.deleteSpeciesComment, name="deleteSpeciesComment"), 
    path('speciesReferenceLinks/', views.speciesReferenceLinks, name="speciesReferenceLinks"),
    path('createSpeciesReferenceLink/<str:pk>/', views.createSpeciesReferenceLink, name="createSpeciesReferenceLink"),     
    path('editSpeciesReferenceLink/<str:pk>/', views.editSpeciesReferenceLink, name="editSpeciesReferenceLink"),  
    path('deleteSpeciesReferenceLink/<str:pk>/', views.deleteSpeciesReferenceLink, name="deleteSpeciesReferenceLink"),  

    path('speciesInstanceLabels', views.speciesInstanceLabels, name="speciesInstanceLabels"),  
    path('chooseSpeciesInstancesForLabels/<str:pk>/', views.chooseSpeciesInstancesForLabels, name="chooseSpeciesInstancesForLabels"),  
    path('editSpeciesInstanceLabels', views.editSpeciesInstanceLabels, name="editSpeciesInstanceLabels"),  

    path('speciesSearch/', views.SpeciesListView.as_view(), name="speciesSearch"),
    #path('', SpeciesListView.as_view(), name='species_list'),

    path('searchSpecies/', views.searchSpecies, name="searchSpecies"),
    path('exportSpecies/', views.exportSpecies, name="exportSpecies"),
    path('importSpecies/', views.importSpecies, name="importSpecies"),

    path('speciesInstance/<str:pk>/', views.speciesInstance, name="speciesInstance"), 
    path('createSpeciesInstance/<str:pk>/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('editSpeciesInstance/<str:pk>/', views.editSpeciesInstance, name="editSpeciesInstance"),
    path('deleteSpeciesInstance/<str:pk>/', views.deleteSpeciesInstance, name="deleteSpeciesInstance"), 

    path('speciesInstancesWithLogs/', views.speciesInstancesWithLogs, name="speciesInstancesWithLogs"),
    path('speciesInstanceLog/<str:pk>/', views.speciesInstanceLog, name="speciesInstanceLog"), 
    path('createSpeciesInstanceLogEntry/<str:pk>/', views.createSpeciesInstanceLogEntry, name="createSpeciesInstanceLogEntry"),
    path('editSpeciesInstanceLogEntry/<str:pk>/', views.editSpeciesInstanceLogEntry, name="editSpeciesInstanceLogEntry"),
    path('deleteSpeciesInstanceLogEntry/<str:pk>/', views.deleteSpeciesInstanceLogEntry, name="deleteSpeciesInstanceLogEntry"),

    path('speciesMaintenanceLogs/', views.speciesMaintenanceLogs, name="speciesMaintenanceLogs"),
    path('speciesMaintenanceLog/<str:pk>/', views.speciesMaintenanceLog, name="speciesMaintenanceLog"), 
    path('createSpeciesMaintenanceLog/<str:pk>/', views.createSpeciesMaintenanceLog, name="createSpeciesMaintenanceLog"),
    path('editSpeciesMaintenanceLog/<str:pk>/', views.editSpeciesMaintenanceLog, name="editSpeciesMaintenanceLog"),
    path('addMaintenanceGroupCollaborator/<str:pk>/', views.addMaintenanceGroupCollaborator, name="addMaintenanceGroupCollaborator"), 
    path('removeMaintenanceGroupCollaborator/<str:pk>/', views.removeMaintenanceGroupCollaborator, name="removeMaintenanceGroupCollaborator"), 
    path('addMaintenanceGroupSpecies/<str:pk>/', views.addMaintenanceGroupSpecies, name="addMaintenanceGroupSpecies"),
    path('removeMaintenanceGroupSpecies/<str:pk>/', views.removeMaintenanceGroupSpecies, name="removeMaintenanceGroupSpecies"),

    path('deleteSpeciesMaintenanceLog/<str:pk>/', views.deleteSpeciesMaintenanceLog, name="deleteSpeciesMaintenanceLog"),
    path('createSpeciesMaintenanceLogEntry/<str:pk>/', views.createSpeciesMaintenanceLogEntry, name="createSpeciesMaintenanceLogEntry"),
    path('editSpeciesMaintenanceLogEntry/<str:pk>/', views.editSpeciesMaintenanceLogEntry, name="editSpeciesMaintenanceLogEntry"),
    path('deleteSpeciesMaintenanceLogEntry/<str:pk>/', views.deleteSpeciesMaintenanceLogEntry, name="deleteSpeciesMaintenanceLogEntry"),

    path('exportSpeciesInstances/', views.exportSpeciesInstances, name="exportSpeciesInstances"),
    path('importSpeciesInstances/', views.importSpeciesInstances, name="importSpeciesInstances"),

    path('addSpeciesInstanceWizard1/', views.addSpeciesInstanceWizard1, name="addSpeciesInstanceWizard1"),
    path('addSpeciesInstanceWizard2/', views.addSpeciesInstanceWizard2, name="addSpeciesInstanceWizard2"),
    
    path('about_us/', views.about_us, name="about_us"),
    path('howItWorks/', views.howItWorks, name="howItWorks"),
    path('tools/', views.tools, name="tools"),

    path('importArchiveResults/<str:pk>/', views.importArchiveResults, name="importArchiveResults"),

    # re_path configuration for media files solves production error with nginx serving up image files
    re_path(r'^media/(?P<path>.*)$', serve,{'document_root': settings.MEDIA_ROOT}),
]

# extend urlpatterns to support Media images uploaded by user - development DEBUG environment
urlpatterns = urlpatterns + static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT)

