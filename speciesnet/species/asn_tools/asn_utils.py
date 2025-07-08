from species.models import User, Species, SpeciesReferenceLink, SpeciesComment, SpeciesInstance, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry
from species.models import CaresRegistration
from datetime import datetime
from django.utils import timezone
import logging

# user_can_edit

def user_can_edit (cur_user: User):
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    return userCanEdit

def user_can_edit_a (cur_user: User, aquarist: User):
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True      
    elif aquarist == cur_user:
        userCanEdit = True
    return userCanEdit

def user_can_edit_s (cur_user: User, species: Species):
    created_date = species.created.date()
    today_date = datetime.today().date()
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    elif created_date == today_date:
        userCanEdit = True       # Allow everyone to edit newly created species on same day of creation
    return userCanEdit

def user_can_edit_si (cur_user: User, speciesInstance: SpeciesInstance):
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True      
    elif speciesInstance.user == cur_user:
        userCanEdit = True
    return userCanEdit

def user_can_edit_srl (cur_user: User, speciesReferenceLink: SpeciesReferenceLink):
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    elif speciesReferenceLink.user == cur_user:
        userCanEdit = True
    return userCanEdit

def user_can_edit_sc (cur_user: User, speciesComment: SpeciesComment):
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True
    elif speciesComment.user == cur_user:
        userCanEdit = True
    return userCanEdit

def user_can_edit_sml (cur_user: User, speciesMaintenanceLog: SpeciesMaintenanceLog):
    speciesInstances = speciesMaintenanceLog.speciesInstances
    userCanEdit = False
    if cur_user.is_staff:
        userCanEdit = True       
    else:
        for speciesInstance in speciesInstances.all():
            if speciesInstance.user == cur_user:
                userCanEdit = True;                   # allow all contributors to edit/delete
    return userCanEdit

def get_sml_available_collaborators (speciesMaintenanceLog: SpeciesMaintenanceLog):
    species = speciesMaintenanceLog.species
    collaborators = speciesMaintenanceLog.collaborators.all()
    allSpeciesInstances = SpeciesInstance.objects.filter(species=species, currently_keep=True)
    available_collaborators = []
    for speciesInstance in allSpeciesInstances:
        if speciesInstance.user not in collaborators:
            if speciesInstance.user not in available_collaborators:
                available_collaborators.append (speciesInstance.user)
    return available_collaborators

def get_sml_collaborator_choices (speciesMaintenanceLog: SpeciesMaintenanceLog):
    species = speciesMaintenanceLog.species
    speciesInstances = SpeciesInstance.objects.filter(species=species, currently_keep=True)
    collaborators = speciesMaintenanceLog.collaborators.all()
    choices = []
    for speciesInstance in speciesInstances:
        choice = (str(speciesInstance.user.id), speciesInstance.user.username)
        if choice not in choices and speciesInstance.user not in collaborators:
            choices.append(choice)
    return choices

def get_sml_available_speciesInstances (speciesMaintenanceLog: SpeciesMaintenanceLog):
    species = speciesMaintenanceLog.species
    collaborators = speciesMaintenanceLog.collaborators.all()
    curSpeciesInstances = speciesMaintenanceLog.speciesInstances.all()
    allSpeciesInstances = SpeciesInstance.objects.filter(species=species, currently_keep=True)
    available_speciesInstances = []
    for speciesInstance in allSpeciesInstances:
        if speciesInstance not in curSpeciesInstances and speciesInstance.user in collaborators:
            available_speciesInstances.append (speciesInstance)
    return available_speciesInstances

def get_sml_speciesInstance_choices (speciesMaintenanceLog: SpeciesMaintenanceLog):
    species = speciesMaintenanceLog.species
    groupSpeciesInstances = speciesMaintenanceLog.speciesInstances.all()
    collaborators = speciesMaintenanceLog.collaborators.all()
    speciesInstances = SpeciesInstance.objects.filter(species=species, currently_keep=True)
    choices = []
    for speciesInstance in speciesInstances:
        choice = (speciesInstance.id, speciesInstance.name)
        if choice not in choices and speciesInstance not in groupSpeciesInstances and speciesInstance.user in collaborators:
            choices.append(choice)
    return choices

def get_cares_approver_user (approver_enum: CaresRegistration.CaresApproverGroup):
    approver = User.objects.get(username = 'BigKahoona')
    if approver_enum == CaresRegistration.CaresApproverGroup.CICHLIDS_TANGANYIKA:
        approver = User.objects.get(username = 'sme_cichlids_tanganyika')
    elif approver_enum == CaresRegistration.CaresApproverGroup.CICHLIDS_MALAWI:
        approver = User.objects.get(username = 'sme_cichlids_malawi')
    elif approver_enum == CaresRegistration.CaresApproverGroup.CICHLIDS_CAMERICA:
        approver = User.objects.get(username = 'sme_cichlids_c_america')
    elif approver_enum == CaresRegistration.CaresApproverGroup.CICHLIDS_SAMERICA:
        approver = User.objects.get(username = 'sme_cichlids_s_america')
    elif approver_enum == CaresRegistration.CaresApproverGroup.CICHLIDS_EAFRICA:
        approver = User.objects.get(username = 'sme_cichlids_e_africa')
    elif approver_enum == CaresRegistration.CaresApproverGroup.BLUEEYES:
        approver = User.objects.get(username = 'sme_cares_blueeyes')
    elif approver_enum == CaresRegistration.CaresApproverGroup.LIVEBEARERS:
        approver = User.objects.get(username = 'sme_cares_livebearers')
    elif approver_enum == CaresRegistration.CaresApproverGroup.ANABANTIDS:
        approver = User.objects.get(username = 'sme_cares_anabantids')
    elif approver_enum == CaresRegistration.CaresApproverGroup.GOODEIDS:
        approver = User.objects.get(username = 'sme_cares_goodeids')
    elif approver_enum == CaresRegistration.CaresApproverGroup.KILLIFISH:
        approver = User.objects.get(username = 'sme_cares_killifish')       
    return approver

def get_cares_approver_enum (species: Species):
    approver_enum = CaresRegistration.CaresApproverGroup.UNASSIGNED
    if species.cares_category == Species.CaresCategory.CICHLIDS:
        species_distribution = species.get_global_region_display()
        species_distribution = species.local_distribution + ' ' + species_distribution
        print ('species_distribution: ' + species_distribution)
        if 'Tanganyika' in species_distribution:
            approver_enum = CaresRegistration.CaresApproverGroup.CICHLIDS_TANGANYIKA
            print ('setting approver_enum: CICHLIDS_TANGANYIKA')
        elif 'Central America' in species_distribution:
            approver_enum = CaresRegistration.CaresApproverGroup.CICHLIDS_CAMERICA
            print ('setting approver_enum: CICHLIDS_CAMERICA')
    elif species.cares_category == Species.CaresCategory.BLUEEYES:
        approver_enum = CaresRegistration.CaresApproverGroup.BLUEEYES
    elif species.cares_category == Species.CaresCategory.LIVEBEARERS:
        approver_enum = CaresRegistration.CaresApproverGroup.LIVEBEARERS
    elif species.cares_category == Species.CaresCategory.ANABANTIDS:
        approver_enum = CaresRegistration.CaresApproverGroup.ANABANTIDS
    elif species.cares_category == Species.CaresCategory.GOODEIDS:
        approver_enum = CaresRegistration.CaresApproverGroup.GOODEIDS
    elif species.cares_category == Species.CaresCategory.KILLIFISH:
        approver_enum = CaresRegistration.CaresApproverGroup.KILLIFISH
    return approver_enum

def validate_sml_collection (speciesMaintenanceLog: SpeciesMaintenanceLog):
    return True

