from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from species.models import User, Species, SpeciesReferenceLink, SpeciesComment, SpeciesInstance
from species.models import SpeciesMaintenanceLog, AquaristClub, AquaristClubMember
from species.models import BapSubmission
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

def user_can_edit_club (cur_user: User, club: AquaristClub):
    userCanEdit = False
    if cur_user.is_staff:
         userCanEdit = True
    else:
        print ('user_can_edit_club: seeing if member exists')
        try:
            member = AquaristClubMember.objects.get(user=cur_user, club=club) 
            userCanEdit = member.is_club_admin
            print ('Club Member is club admin: ' + cur_user.username)
        except ObjectDoesNotExist:
            pass # user is not a member 
            print ('Club Member not found: ' + cur_user.username + ' can join')
        except MultipleObjectsReturned:
            error_msg = "Club Members: duplicate members found!"
            print ('Error multiple objects found AquaristClubMember: ' + cur_user.username)
            #TODO logging
    return userCanEdit


def user_is_club_member (cur_user: User, club: AquaristClub):
    user_is_member = False
    try:
        member = AquaristClubMember.objects.get(user=cur_user, club=club) 
        user_is_member = True
        print ('Club Member found: ' + cur_user.username)
    except ObjectDoesNotExist:
        pass # user is not a member 
    except MultipleObjectsReturned:
        error_msg = "Club Members: duplicate members found!"
        print ('Error multiple objects found AquaristClubMember: ' + cur_user.username)
        logger.error('Club member check: multiple entries found for %s', cur_user.username)
    return user_is_member

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

def validate_sml_collection (speciesMaintenanceLog: SpeciesMaintenanceLog):
    return True

