"""
Species views package
"""

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
    exportSpecies, importSpecies
)

# Species Instance (Aquarist Species)
from .views_species_instance import (
    speciesInstance, createSpeciesInstance, editSpeciesInstance, deleteSpeciesInstance,
    createSpeciesAndInstance, speciesInstanceLog, createSpeciesInstanceLogEntry,
    editSpeciesInstanceLogEntry, deleteSpeciesInstanceLogEntry,
    speciesInstanceLabels, chooseSpeciesInstancesForLabels, editSpeciesInstanceLabels,
    exportSpeciesInstances, importSpeciesInstances
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
    deleteAquaristClubMember
)

# CLub BAP
from .views_bap import (
    bapSubmission, createBapSubmission, editBapSubmission, deleteBapSubmission,
    BapSubmissionsView, BapLeaderboardView, BapGenusView, BapSpeciesView,
    BapGenusSpeciesView, editBapGenus, deleteBapGenus, createBapSpecies,
    editBapSpecies, deleteBapSpecies, importClubBapGenus, exportClubBapGenus, 
    bap_submissions_overview
)

# User Experience
from .views_ux import (
    home, about_us, howItWorks, bap_overview, cares_overview, 
    importArchiveResults, addSpeciesInstanceWizard1, addSpeciesInstanceWizard2
)

# Admin Tools
from .views_tools import (
    speciesInstancesWithLogs, speciesInstancesWithEmptyLogs, speciesInstancesWithVideos,
    tools, tools2, dirtyDeed
)

# Make all views available at package level
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
    'editSpeciesInstanceLogEntry', 'deleteSpeciesInstanceLogEntry', 'speciesInstanceLabels', 
    'chooseSpeciesInstancesForLabels', 'editSpeciesInstanceLabels',
       
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
    'deleteAquaristClubMember',
    
    # BAP
    'bapSubmission', 'createBapSubmission', 'editBapSubmission', 'deleteBapSubmission',
    'BapSubmissionsView', 'BapLeaderboardView', 'BapGenusView', 'BapSpeciesView',
    'BapGenusSpeciesView', 'editBapGenus', 'deleteBapGenus', 'createBapSpecies',
    'editBapSpecies', 'deleteBapSpecies',
    
    # Import
    'exportSpecies', 'importSpecies', 'exportAquarists', 'exportSpeciesInstances',
    'importSpeciesInstances', 'importClubBapGenus', 'exportClubBapGenus',
    'importArchiveResults',
    
    # UX
    'home', 'about_us', 'howItWorks', 
    'bap_overview', 'bap_submissions_overview', 'cares_overview', 

    # Admin Tools
    'speciesInstancesWithLogs', 'speciesInstancesWithEmptyLogs', 'speciesInstancesWithVideos',
    'tools', 'tools2',  'dirtyDeed'
]