from django.urls import path, re_path
from django.conf.urls.static import static
from django.views.static import serve
#from django.conf.urls import url - deprecated
from django.conf import settings
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('about_us/', views.about_us, name="about_us"),
    path('howItWorks/', views.howItWorks, name="howItWorks"),

    ### Users == Aquarists ###

    path('login/', views.loginUser, name="login"),
    path('logout/', views.logoutUser, name="logout"), 
    #path('register/', views.registerUser, name="register"), 
    path('userProfile/', views.userProfile, name="userProfile"),
    path('editUserProfile/', views.editUserProfile, name="editUserProfile"),

    path('aquarist/<str:pk>/', views.aquarist, name="aquarist"),
    path('aquarists/', views.AquaristListView.as_view(), name="aquarists"),
    path('emailAquarist/<str:pk>/', views.emailAquarist, name="emailAquarist"),
    path('exportAquarists/', views.exportAquarists, name="exportAquarists"),

    ### Aquarist Clubs ###

    path('aquaristClubs/', views.aquaristClubs, name="aquaristClubs"),
    path('aquaristClub/<str:pk>/', views.aquaristClub, name="aquaristClub"), 
    path('createAquaristClub/', views.createAquaristClub, name="createAquaristClub"),
    path('editAquaristClub/<str:pk>/', views.editAquaristClub, name="editAquaristClub"),
    path('deleteAquaristClub/<str:pk>/', views.deleteAquaristClub, name="deleteAquaristClub"), 
    path('exportAquaristClubs/', views.exportAquaristClubs, name="exportAquaristClubs"),
    #path('importAquaristClubs/', views.importAquaristClubs, name="importAquaristClubs"),

    path('aquaristClubMember/<int:pk>/', views.aquaristClubMember, name="aquaristClubMember"), 
    path('aquaristClubAdmin/<str:pk>/', views.aquaristClubAdmin, name="aquaristClubAdmin"),
    path('aquaristClubMembers/<str:pk>/', views.AquaristClubMemberListView.as_view(), name="aquaristClubMembers"), 
    path('createAquaristClubMember/<str:pk>', views.createAquaristClubMember, name="createAquaristClubMember"),
    path('editAquaristClubMember/<str:pk>/', views.editAquaristClubMember, name="editAquaristClubMember"),
    path('deleteAquaristClubMember/<str:pk>/', views.deleteAquaristClubMember, name="deleteAquaristClubMember"), 
    path('exportAquaristClubMembers/', views.exportAquaristClubMembers, name="exportAquaristClubMembers"),

    ### Aquarist Club BAP Programs ###

    path('bapSubmission/<str:pk>/', views.bapSubmission, name="bapSubmission"),
    path('bapSubmissions/<str:pk>/', views.BapSubmissionsView.as_view(), name="bapSubmissions"),
    path('createBapSubmission/<str:pk>/', views.createBapSubmission, name="createBapSubmission"),
    path('editBapSubmission/<str:pk>/', views.editBapSubmission, name="editBapSubmission"),
    path('deleteBapSubmission/<str:pk>/', views.deleteBapSubmission, name="deleteBapSubmission"),
    path('exportBapSubmissions/', views.exportBapSubmissions, name="exportBapSubmissions"),

    path('bapGenus/<str:pk>/', views.BapGenusView.as_view(), name="bapGenus"),
    path('editBapGenus/<str:pk>/', views.editBapGenus, name="editBapGenus"),
    path('deleteBapGenus/<str:pk>/', views.deleteBapGenus, name="deleteBapGenus"),

    path('bapSpecies/<str:pk>/', views.BapSpeciesView.as_view(), name="bapSpecies"),
    path('createBapSpecies/<str:pk>/', views.createBapSpecies, name="createBapSpecies"),
    path('editBapSpecies/<str:pk>/', views.editBapSpecies, name="editBapSpecies"),
    path('deleteBapSpecies/<str:pk>/', views.deleteBapSpecies, name="deleteBapSpecies"),

    path('bapGenusSpecies/<str:pk>/', views.BapGenusSpeciesView.as_view(), name="bapGenusSpecies"),    
    
    path('bapLeaderboard/<str:pk>/', views.BapLeaderboardView.as_view(), name="bapLeaderboard"),
    path('bap_overview/', views.bap_overview, name="bap_overview"),
    path('bap_submissions_overview/', views.bap_submissions_overview, name="bap_submissions_overview"),

    path('species/import/importClubBapGenus/<str:pk>/', views.importClubBapGenus, name="importClubBapGenus"),
    path('exportClubBapGenus/<str:pk>/', views.exportClubBapGenus, name="exportClubBapGenus"),

    ### Species == 'Species Profiles' (UX) ###

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

    ### CARES ASN or Shared ###
    
    path('cares_overview/', views.cares_overview, name="cares_overview"),
    path('caresLiaisonDashboard/<str:pk>/', views.AquaristClubCaresLiaisonListView.as_view(), name="caresLiaisonDashboard"), 
    path('registerCaresSpeciesInstance/<str:pk>/', views.registerCaresSpeciesInstance, name="registerCaresSpeciesInstance"),

    ### CARES Site 2 Only ###

    path('caresSpecies/<str:pk>/', views.caresSpecies, name="caresSpecies"), 
    path('createCaresSpecies/', views.createCaresSpecies, name="createCaresSpecies"),
    path('editCaresSpecies/<str:pk>/', views.editCaresSpecies, name="editCaresSpecies"),
    path('editCaresSpecies2/<str:pk>/', views.editCaresSpecies2, name="editCaresSpecies2"),
    path('deleteCaresSpecies/<str:pk>/', views.deleteCaresSpecies, name="deleteCaresSpecies"),
    path('cares/caresSpeciesSearch/', views.CaresSpeciesListView.as_view(), name="caresSpeciesSearch"),

    path('caresRegistration/<str:pk>/', views.caresRegistration, name="caresRegistration"), 
    path('cares/caresRegistrations/', views.CaresRegistrationListView.as_view(), name="caresRegistrations"),
    path('createCaresRegistration/<str:pk>/', views.createCaresRegistration, name="createCaresRegistration"),
    path('editCaresRegistration/<str:pk>/', views.editCaresRegistration, name="editCaresRegistration"),
    path('editCaresRegistrationAdmin/<str:pk>/', views.editCaresRegistrationAdmin, name="editCaresRegistrationAdmin"),
    path('deleteCaresRegistration/<str:pk>/', views.deleteCaresRegistration, name="deleteCaresRegistration"),

    path('registerCaresSpecies/<str:pk>/', views.registerCaresSpecies, name="registerCaresSpecies"),             # annonymous user registration
    path('registerCaresSelectSpecies/', views.registerCaresSelectSpecies, name="registerCaresSelectSpecies"),    # annonymous user registration
    path('registrationLookup/', views.registrationLookup, name="registrationLookup"),                            # annonymous user reg check

    path('exportCaresRegistrations/', views.exportCaresRegistrations, name="exportCaresRegistrations"),
    path('importCaresRegistrations/', views.importCaresRegistrations, name="importCaresRegistrations"),
    path('exportCaresRegistrationsPending/', views.exportCaresRegistrationsPending, name="exportCaresRegistrationsPending"),

    path('caresApprover/<str:pk>/', views.caresApprover, name="caresApprover"),
    path('createCaresApprover/', views.createCaresApprover, name="createCaresApprover"),
    path('editCaresApprover/<str:pk>/', views.editCaresApprover, name="editCaresApprover"),
    path('deleteCaresApprover/<str:pk>/', views.deleteCaresApprover, name="deleteCaresApprover"),    
    path('caresApprovers/', views.caresApprovers, name="caresApprovers"), 

    ### Species == Species Profile (UX) ###

    path('speciesSearch/', views.SpeciesListView.as_view(), name="speciesSearch"),
    path('exportSpecies/', views.exportSpecies, name="exportSpecies"),
    #path('importSpecies/', views.importSpecies, name="importSpecies"),

    ### Species Instance == Aquarist Species (UX) ###

    path('speciesInstance/<str:pk>/', views.speciesInstance, name="speciesInstance"), 
    path('createSpeciesInstance/<str:pk>/', views.createSpeciesInstance, name="createSpeciesInstance"),
    path('editSpeciesInstance/<str:pk>/', views.editSpeciesInstance, name="editSpeciesInstance"),
    path('deleteSpeciesInstance/<str:pk>/', views.deleteSpeciesInstance, name="deleteSpeciesInstance"), 
    path('reassignSpeciesInstance/<str:pk>/', views.reassignSpeciesInstance, name="reassignSpeciesInstance"), 
    
    path('createSpeciesAndInstance/', views.createSpeciesAndInstance, name="createSpeciesAndInstance"), 

    path('chooseSpeciesInstancesForLabels/<str:pk>/', views.chooseSpeciesInstancesForLabels, name="chooseSpeciesInstancesForLabels"),  
    path('editSpeciesInstanceLabels', views.editSpeciesInstanceLabels, name="editSpeciesInstanceLabels"),      

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
    #path('importSpeciesInstances/', views.importSpeciesInstances, name="importSpeciesInstances"),

    path('addSpeciesInstanceWizard1/', views.addSpeciesInstanceWizard1, name="addSpeciesInstanceWizard1"),
    path('addSpeciesInstanceWizard2/', views.addSpeciesInstanceWizard2, name="addSpeciesInstanceWizard2"),

    ### Admin Tools - Multiple Levels ###

    path('tools/', views.tools, name="tools"),      # Level 1 Species Admins
    path('tools2/', views.tools2, name="tools2"),   # Level 2 Staff and Level 3 Admin-only

    path('speciesInstancesWithLabels', views.speciesInstancesWithLabels, name="speciesInstancesWithLabels"),  
    path('speciesInstancesWithVideos/', views.speciesInstancesWithVideos, name="speciesInstancesWithVideos"),
    path('speciesInstancesWithLogs/', views.speciesInstancesWithLogs, name="speciesInstancesWithLogs"),
    path('speciesInstancesWithEmptyLogs/', views.speciesInstancesWithEmptyLogs, name="speciesInstancesWithEmptyLogs"),
    path('speciesInstancesWithPhotos/', views.speciesInstancesWithPhotos, name="speciesInstancesWithPhotos"),
    path('speciesProfilesWithPhotos/', views.speciesProfilesWithPhotos, name="speciesProfilesWithPhotos"),

    path('species/import/importArchiveResults/<str:pk>/', views.importArchiveResults, name="importArchiveResults"),    # admin-only
    path('collectSpeciesData/', views.collectSpeciesData, name="collectSpeciesData"),                   # admin-only
    path('dirtyDeed/', views.dirtyDeed, name="dirtyDeed"),                                              # admin-only

    ### Species Import Workflow ###

    path('speciesImportToStaging/', views.importSpeciesToStaging, name="importSpeciesToStaging"),
    path('speciesImportReview/<str:pk>/', views.reviewSpeciesImport, name="reviewSpeciesImport"),
    path('speciesImportReviewDetail/<str:staging_id>/', views.reviewSpeciesImportDetail, name="reviewSpeciesImportDetail"),
    path('species/import/approve/<str:pk>/', views.approveSpeciesImportBatch, name="approveSpeciesImportBatch"),
    path('species/import/reject/<str:pk>/', views.rejectSpeciesImportBatch, name="rejectSpeciesImportBatch"),
    path('species/import/commit/<str:pk>/', views.commitSpeciesImport, name="commitSpeciesImport"),
    path('species/import/referenceLinks/', views.importSpeciesReferenceLinks, name="importSpeciesReferenceLinks"),

    ### Species Feedback ###

    path('species/<int:pk>/feedback/', views.submitSpeciesFeedback, name='submitSpeciesFeedback'),
    path('tools/species-feedback/', views.speciesFeedbackTools, name='speciesFeedbackTools'),
    path('tools/species-feedback/<int:pk>/apply-photo/', views.applySpeciesFeedbackPhoto, name='applySpeciesFeedbackPhoto'),
    path('tools/species-feedback/<int:pk>/archive/', views.archiveSpeciesFeedback, name='archiveSpeciesFeedback'),
    path('tools/species-feedback/<int:pk>/delete/', views.deleteSpeciesFeedback, name='deleteSpeciesFeedback'),

    # django: re_path configuration for media files solves production error with nginx serving up image files
    re_path(r'^media/(?P<path>.*)$', serve,{'document_root': settings.MEDIA_ROOT}),
]

# django: extend urlpatterns to support Media images uploaded by user - development DEBUG environment
urlpatterns = urlpatterns + static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT)

