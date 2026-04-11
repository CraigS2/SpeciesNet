"""
Species views package
"""

### Adding Views requires:
### 1: importing the view from the appropriate file -- see IMPORT
### 2: making the view available from the package   -- see PACKAGE


### IMPORT from view .py files

# User & Authentication
from .views_user import (
    userProfile, editUserProfile, aquarist, AquaristListView,
    loginUser, logoutUser, emailAquarist,  exportAquarists
)

# Species (Species Profiles)
from .views_species import (
    species, createSpecies, editSpecies, deleteSpecies, SpeciesListView, 
    createSpeciesReferenceLink, editSpeciesReferenceLink, deleteSpeciesReferenceLink,
    speciesReferenceLinks, speciesComments, editSpeciesComment, deleteSpeciesComment,
    exportSpecies#, importSpecies
)

# Species (Species Profiles)
from .views_cares import (
    caresSpecies, createCaresSpecies, editCaresSpecies, deleteCaresSpecies, CaresSpeciesListView,
    caresRegistration, createCaresRegistration, editCaresRegistration, deleteCaresRegistration, 
    CaresRegistrationListView, registerCaresSelectSpecies, registerCaresSpecies, 
    editCaresSpecies2, editCaresRegistrationAdmin, registrationLookup,
    caresApprover, createCaresApprover, editCaresApprover, deleteCaresApprover, caresApprovers,
    exportCaresRegistrations, importCaresRegistrations,
)

# Species Instance (Aquarist Species)
from .views_species_instance import (
    speciesInstance, createSpeciesInstance, editSpeciesInstance, deleteSpeciesInstance,
    createSpeciesAndInstance, speciesInstanceLog, createSpeciesInstanceLogEntry,
    editSpeciesInstanceLogEntry, deleteSpeciesInstanceLogEntry, chooseSpeciesInstancesForLabels, editSpeciesInstanceLabels,
    reassignSpeciesInstance, exportSpeciesInstances,
    registerCaresSpeciesInstance
)

# Maintenance Logs
from .views_maintenance_log import (
    speciesMaintenanceLogs, speciesMaintenanceLog, createSpeciesMaintenanceLog,
    editSpeciesMaintenanceLog, deleteSpeciesMaintenanceLog,
    createSpeciesMaintenanceLogEntry, editSpeciesMaintenanceLogEntry,
    deleteSpeciesMaintenanceLogEntry, addMaintenanceGroupCollaborator,
    removeMaintenanceGroupCollaborator, addMaintenanceGroupSpecies,
    removeMaintenanceGroupSpecies
)

# Aquarist Clubs
from .views_club import (
    aquaristClubs, aquaristClub, createAquaristClub, editAquaristClub,
    deleteAquaristClub, aquaristClubAdmin, AquaristClubMemberListView,
    aquaristClubMember, createAquaristClubMember, editAquaristClubMember,
    deleteAquaristClubMember, AquaristClubCaresLiaisonListView,
    exportAquaristClubs, exportAquaristClubMembers
)

# CLub BAP
from .views_bap import (
    bapSubmission, createBapSubmission, editBapSubmission, deleteBapSubmission,
    BapSubmissionsView, bap_submissions_overview,
    BapLeaderboardView, BapGenusView, BapSpeciesView, BapGenusSpeciesView,
    createBapSpecies, editBapSpecies, deleteBapSpecies, 
    editBapGenus, deleteBapGenus,
    importClubBapGenus, exportClubBapGenus, exportBapSubmissions
)

# User Experience
from .views_ux import (
    home, about_us, howItWorks, bap_overview, cares_overview, 
    importArchiveResults, addSpeciesInstanceWizard1, addSpeciesInstanceWizard2
)

# Admin Tools
from .views_tools import (
    speciesProfilesWithPhotos, speciesInstancesWithPhotos, speciesInstancesWithLabels, 
    speciesInstancesWithLogs, speciesInstancesWithEmptyLogs, speciesInstancesWithVideos,
    collectSpeciesData, 
    tools, tools2, dirtyDeed
)

# Species Import with Review-Approve Workflow
from .views_species_import import (
    importSpeciesToStaging, reviewSpeciesImport, reviewSpeciesImportDetail,
    approveSpeciesImportBatch, rejectSpeciesImportBatch, commitSpeciesImport,
    importSpeciesReferenceLinks,
)

# Species Feedback
from .views_feedback import (
    submitSpeciesFeedback, speciesFeedbackTools, approveSpeciesFeedback, deleteSpeciesFeedback,
)


### PACKAGE view declarations

__all__ = [
    # User
    'userProfile', 'editUserProfile', 'aquarist', 'AquaristListView',
    'loginUser', 'logoutUser', 'emailAquarist', 
    
    # Species
    'species', 'createSpecies', 'editSpecies', 'deleteSpecies', 'SpeciesListView', 
    'addSpeciesInstanceWizard1', 'addSpeciesInstanceWizard2', 'createSpeciesReferenceLink', 
    'editSpeciesReferenceLink', 'deleteSpeciesReferenceLink', 'speciesReferenceLinks', 
    'speciesComments', 'editSpeciesComment', 'deleteSpeciesComment',
    
    # Species Instances
    'speciesInstance', 'createSpeciesInstance', 'editSpeciesInstance', 'deleteSpeciesInstance',
    'createSpeciesAndInstance', 'speciesInstanceLog', 'createSpeciesInstanceLogEntry',
    'editSpeciesInstanceLogEntry', 'deleteSpeciesInstanceLogEntry', 'speciesInstancesWithLabels', 
    'speciesInstancesWithPhotos','chooseSpeciesInstancesForLabels', 'editSpeciesInstanceLabels',
    'registerCaresSpeciesInstance',
       
    # Maintenance Logs
    'speciesMaintenanceLogs', 'speciesMaintenanceLog', 'createSpeciesMaintenanceLog',
    'editSpeciesMaintenanceLog', 'deleteSpeciesMaintenanceLog',
    'createSpeciesMaintenanceLogEntry', 'editSpeciesMaintenanceLogEntry',
    'deleteSpeciesMaintenanceLogEntry', 'addMaintenanceGroupCollaborator',
    'removeMaintenanceGroupCollaborator', 'addMaintenanceGroupSpecies',
    'removeMaintenanceGroupSpecies',
    
    # Clubs
    'aquaristClubs', 'aquaristClub', 'createAquaristClub', 'editAquaristClub',
    'deleteAquaristClub', 'aquaristClubAdmin', 'AquaristClubMemberListView',
    'aquaristClubMember', 'createAquaristClubMember', 'editAquaristClubMember',
    'deleteAquaristClubMember', AquaristClubCaresLiaisonListView,

    # Cares
    'caresRegistration', 'createCaresRegistration', 'editCaresRegistration', 'deleteCaresRegistration', 
    'caresApprover', 'createCaresApprover', 'editCaresApprover', 'deleteCaresApprover',
    'registerCaresSelectSpecies', 'registerCaresSpecies', 'registrationLookup',
    
    # BAP
    'bapSubmission', 'createBapSubmission', 'editBapSubmission', 'deleteBapSubmission',
    'BapSubmissionsView', 'BapLeaderboardView', 'BapGenusView', 'BapSpeciesView',
    'BapGenusSpeciesView', 'editBapGenus', 'deleteBapGenus', 'createBapSpecies',
    'editBapSpecies', 'deleteBapSpecies',
    
    # Import
    'exportSpecies', 'exportAquarists', 'exportSpeciesInstances',
    'importClubBapGenus', 'exportClubBapGenus',
    'importArchiveResults',
    
    # UX
    'home', 'about_us', 'howItWorks', 
    'bap_overview', 'bap_submissions_overview', 'cares_overview', 

    # Admin Tools
    'speciesInstancesWithLogs', 'speciesInstancesWithEmptyLogs', 'speciesInstancesWithVideos',
    'tools', 'tools2',  'dirtyDeed',

    # CARES Import Workflow
    'importSpeciesToStaging', 'reviewSpeciesImport', 'reviewSpeciesImportDetail',
    'approveSpeciesImportBatch', 'rejectSpeciesImportBatch', 'commitSpeciesImport',

    # Species Reference Link Import
    'importSpeciesReferenceLinks',

    # Species Feedback
    'submitSpeciesFeedback', 'speciesFeedbackTools', 'approveSpeciesFeedback', 'deleteSpeciesFeedback',
] # type: ignore