"""Species views package."""

### Adding Views requires:
### 1: importing the view from the appropriate file -- see IMPORT
### 2: making the view available from the package   -- see PACKAGE


### IMPORT from view .py files

# User & Authentication
# CLub BAP
from .views_bap import (
    BapGenusSpeciesView,
    BapGenusView,
    BapLeaderboardView,
    BapSpeciesView,
    BapSubmissionsView,
    bap_submissions_overview,
    bapSubmission,
    createBapSpecies,
    createBapSubmission,
    deleteBapGenus,
    deleteBapSpecies,
    deleteBapSubmission,
    editBapGenus,
    editBapSpecies,
    editBapSubmission,
    exportBapSubmissions,
    exportClubBapGenus,
    importClubBapGenus,
)

# CARES
from .views_cares import (
    CaresRegistrationListView,
    CaresSpeciesListView,
    caresApprover,
    caresApprovers,
    caresPriorityList,
    caresRegistration,
    caresRegistrationNotifyAquarist,
    caresRegistrationsFromAsn,
    caresSpecies,
    createCaresApprover,
    createCaresRegistration,
    createCaresSpecies,
    deleteCaresApprover,
    deleteCaresRegistration,
    deleteCaresSpecies,
    editCaresApprover,
    editCaresRegistration,
    editCaresRegistrationAdmin,
    editCaresSpecies,
    editCaresSpecies2,
    exportCaresRegistrations,
    importCaresLegacyRegistrations,
    importCaresRegistrations,
    importSpeciesExternalIds,
    registerCaresSelectSpecies,
    registerCaresSpecies,
    registrationLookup,
)

# Aquarist Clubs
from .views_club import (
    AquaristClubCaresLiaisonListView,
    AquaristClubMemberListView,
    aquaristClub,
    aquaristClubAdmin,
    aquaristClubMember,
    aquaristClubs,
    createAquaristClub,
    createAquaristClubMember,
    deleteAquaristClub,
    deleteAquaristClubMember,
    editAquaristClub,
    editAquaristClubMember,
    exportAquaristClubMembers,
    exportAquaristClubs,
)

# Species Feedback
from .views_feedback import (
    applySpeciesFeedbackPhoto,
    archiveSpeciesFeedback,
    deleteSpeciesFeedback,
    speciesFeedbackTools,
    submitSpeciesFeedback,
)

# Maintenance Logs
from .views_maintenance_log import (
    addMaintenanceGroupCollaborator,
    addMaintenanceGroupSpecies,
    createSpeciesMaintenanceLog,
    createSpeciesMaintenanceLogEntry,
    deleteSpeciesMaintenanceLog,
    deleteSpeciesMaintenanceLogEntry,
    editSpeciesMaintenanceLog,
    editSpeciesMaintenanceLogEntry,
    removeMaintenanceGroupCollaborator,
    removeMaintenanceGroupSpecies,
    speciesMaintenanceLog,
    speciesMaintenanceLogs,
)

# Page View Counts
from .views_pageviews import pageviewsTopRanking

# CARES Raffle Admin Tools
from .views_raffle import (
    raffle_dashboard,
    raffle_enter,
    raffle_entries,
    raffle_export_entries,
    raffle_export_species_results,
    raffle_mark_account_created,
    raffle_mark_manual_winner,
    raffle_pick_winner,
    raffle_reset,
    raffle_thanks,
    raffle_upload_species,
)

# Species (Species Profiles)
from .views_species import (
    SpeciesListView,
    createSpecies,
    createSpeciesCollectionLocation,
    createSpeciesReferenceLink,
    deleteSpecies,
    deleteSpeciesCollectionLocation,
    deleteSpeciesComment,
    deleteSpeciesReferenceLink,
    editSpecies,
    editSpeciesCollectionLocation,
    editSpeciesComment,
    editSpeciesReferenceLink,
    exportSpecies,  # , importSpecies
    species,
    speciesCollectionLocations,
    speciesComments,
    speciesReferenceLinks,
)

# Species Import with Review-Approve Workflow
from .views_species_import import (
    approveSpeciesImportBatch,
    commitSpeciesImport,
    importSpeciesReferenceLinks,
    importSpeciesToStaging,
    rejectSpeciesImportBatch,
    reviewSpeciesImport,
    reviewSpeciesImportDetail,
)

# Species Instance (Aquarist Species)
from .views_species_instance import (
    chooseSpeciesInstancesForLabels,
    createSpeciesAndInstance,
    createSpeciesInstance,
    createSpeciesInstanceLogEntry,
    deleteSpeciesInstance,
    deleteSpeciesInstanceLogEntry,
    editSpeciesInstance,
    editSpeciesInstanceLabels,
    editSpeciesInstanceLogEntry,
    exportSpeciesInstances,
    reassignSpeciesInstance,
    registerCaresSpeciesInstance,
    speciesInstance,
    speciesInstanceLog,
)

# Admin Tools
from .views_tools import (
    collectionLocations,
    collectSpeciesData,
    dirtyDeed,
    enforceSpeciesNameSingleQuotes,
    exportSpeciesCollectionLocations,
    importSpeciesCollectionLocations,
    importSpeciesInstanceCollectionLocations,
    speciesInstancesWithEmptyLogs,
    speciesInstancesWithLabels,
    speciesInstancesWithLogs,
    speciesInstancesWithPhotos,
    speciesInstancesWithVideos,
    speciesProfilesWithPhotos,
    speciesWithManageCollectionLocations,
    tools,
    tools2,
)
from .views_user import (
    AquaristListView,
    aquarist,
    editUserProfile,
    emailAquarist,
    exportAquarists,
    loginUser,
    logoutUser,
    userProfile,
)

# User Experience
from .views_ux import (
    about_us,
    addSpeciesInstanceWizard1,
    addSpeciesInstanceWizard2,
    bap_overview,
    cares_overview,
    home,
    howItWorks,
    importArchiveResults,
)

### PACKAGE view declarations

__all__ = [
    # User
    "userProfile",
    "editUserProfile",
    "aquarist",
    "AquaristListView",
    "loginUser",
    "logoutUser",
    "emailAquarist",
    # Species
    "species",
    "createSpecies",
    "editSpecies",
    "deleteSpecies",
    "SpeciesListView",
    "addSpeciesInstanceWizard1",
    "addSpeciesInstanceWizard2",
    "createSpeciesReferenceLink",
    "editSpeciesReferenceLink",
    "deleteSpeciesReferenceLink",
    "speciesReferenceLinks",
    "speciesComments",
    "editSpeciesComment",
    "deleteSpeciesComment",
    # Species Instances
    "speciesInstance",
    "createSpeciesInstance",
    "editSpeciesInstance",
    "deleteSpeciesInstance",
    "createSpeciesAndInstance",
    "speciesInstanceLog",
    "createSpeciesInstanceLogEntry",
    "editSpeciesInstanceLogEntry",
    "deleteSpeciesInstanceLogEntry",
    "speciesInstancesWithLabels",
    "speciesInstancesWithPhotos",
    "chooseSpeciesInstancesForLabels",
    "editSpeciesInstanceLabels",
    "registerCaresSpeciesInstance",
    # Maintenance Logs
    "speciesMaintenanceLogs",
    "speciesMaintenanceLog",
    "createSpeciesMaintenanceLog",
    "editSpeciesMaintenanceLog",
    "deleteSpeciesMaintenanceLog",
    "createSpeciesMaintenanceLogEntry",
    "editSpeciesMaintenanceLogEntry",
    "deleteSpeciesMaintenanceLogEntry",
    "addMaintenanceGroupCollaborator",
    "removeMaintenanceGroupCollaborator",
    "addMaintenanceGroupSpecies",
    "removeMaintenanceGroupSpecies",
    # Clubs
    "aquaristClubs",
    "aquaristClub",
    "createAquaristClub",
    "editAquaristClub",
    "deleteAquaristClub",
    "aquaristClubAdmin",
    "AquaristClubMemberListView",
    "aquaristClubMember",
    "createAquaristClubMember",
    "editAquaristClubMember",
    "deleteAquaristClubMember",
    "AquaristClubCaresLiaisonListView",
    # Cares
    "caresRegistration",
    "createCaresRegistration",
    "editCaresRegistration",
    "deleteCaresRegistration",
    "caresRegistrationNotifyAquarist",
    "caresApprover",
    "createCaresApprover",
    "editCaresApprover",
    "deleteCaresApprover",
    "registerCaresSelectSpecies",
    "registerCaresSpecies",
    "registrationLookup",
    # BAP
    "bapSubmission",
    "createBapSubmission",
    "editBapSubmission",
    "deleteBapSubmission",
    "BapSubmissionsView",
    "BapLeaderboardView",
    "BapGenusView",
    "BapSpeciesView",
    "BapGenusSpeciesView",
    "editBapGenus",
    "deleteBapGenus",
    "createBapSpecies",
    "editBapSpecies",
    "deleteBapSpecies",
    # Import
    "exportSpecies",
    "exportAquarists",
    "exportSpeciesInstances",
    "importClubBapGenus",
    "exportClubBapGenus",
    "importArchiveResults",
    # UX
    "home",
    "about_us",
    "howItWorks",
    "bap_overview",
    "bap_submissions_overview",
    "cares_overview",
    # Admin Tools
    "speciesInstancesWithLogs",
    "speciesInstancesWithEmptyLogs",
    "speciesInstancesWithVideos",
    "tools",
    "tools2",
    "dirtyDeed",
    "exportSpeciesCollectionLocations",
    "importSpeciesCollectionLocations",
    "importSpeciesInstanceCollectionLocations",
    # CARES Import Workflow
    "importSpeciesToStaging",
    "reviewSpeciesImport",
    "reviewSpeciesImportDetail",
    "approveSpeciesImportBatch",
    "rejectSpeciesImportBatch",
    "commitSpeciesImport",
    # Species Reference Link Import
    "importSpeciesReferenceLinks",
    # Species Feedback
    "submitSpeciesFeedback",
    "speciesFeedbackTools",
    "approveSpeciesFeedback",
    "deleteSpeciesFeedback",
]
