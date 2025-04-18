from species.models import User, Species, SpeciesReferenceLink, SpeciesComment, SpeciesInstance, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry
from datetime import datetime
from django.utils import timezone
import logging

# user_can_edit

def user_can_edit (cur_user: User):
    userCanEdit = False
    if cur_user.is_staff:
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
        for speciesInstance in speciesInstances:
            if speciesInstances.user == cur_user:
                userCanEdit = True;                   # allow all contributors to edit/delete
    return userCanEdit

def get_sml_available_collaborators (speciesMaintenanceLog: SpeciesMaintenanceLog):
    species = speciesMaintenanceLog.species
    collaborators = speciesMaintenanceLog.collaborators.all()
    allSpeciesInstances = SpeciesInstance.objects.filter(species=species, currently_keep=True)
    available_collaborators = []
    for speciesInstance in allSpeciesInstances:
        if speciesInstance.user not in collaborators:
            print ('addMaintenanceGroupCollaborator adding choice: ' + speciesInstance.user.username)
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
    print ('get_sml_available_speciesInstances found matching species instances: count = ' + str(len(allSpeciesInstances)))
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


    


def validate_sml_collection (speciesMaintenanceLog: SpeciesMaintenanceLog):
    return True

