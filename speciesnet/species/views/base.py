"""
Shared utilities, imports, and base configuration for all views
"""

# Django core
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist, MultipleObjectsReturned
from django.db.utils import IntegrityError
from django.core.mail import EmailMessage
from django.utils import timezone
from django.views.generic import ListView
from smtplib import SMTPException
from csv import DictReader
import logging

# Third party
from pillow_heif import register_heif_opener

# Local models
from species.models import (
    User, AquaristClub, AquaristClubMember, Species, SpeciesComment,
    SpeciesReferenceLink, SpeciesInstance, SpeciesInstanceLabel,
    SpeciesInstanceLogEntry, SpeciesMaintenanceLog, SpeciesMaintenanceLogEntry,
    ImportArchive, BapSubmission, BapLeaderboard, BapGenus, BapSpecies, 
    CaresRegistration, CaresApprover
)

# Local forms
from species.forms import (
    UserProfileForm, EmailAquaristForm, SpeciesForm, SpeciesInstanceForm,
    SpeciesCommentForm, SpeciesReferenceLinkForm, SpeciesForm2, CaresSpeciesForm, SpeciesInstanceForm2,
    CombinedSpeciesForm, SpeciesInstanceLogEntryForm, AquaristClubForm,
    AquaristClubMemberForm, AquaristClubMemberJoinForm, ImportCsvForm,
    SpeciesMaintenanceLogForm, SpeciesMaintenanceLogEntryForm,
    MaintenanceGroupCollaboratorForm, MaintenanceGroupSpeciesForm,
    SpeciesLabelsSelectionForm, SpeciesInstanceLabelFormSet,
    BapSubmissionForm, BapSubmissionFormEdit, BapSubmissionFormAdminEdit,
    BapGenusForm, BapSpeciesForm, BapSubmissionFilterForm,
    CaresRegistrationSubmitionForm, CaresRegistrationApprovalForm, CaresApproverForm,
    CaresRegistrationForm2, CaresSpeciesForm2
)

# Local utilities
from species.asn_tools.asn_img_tools import processUploadedImageFile, generate_qr_code
from species.asn_tools.asn_csv_tools import (
    export_csv_species, export_csv_speciesInstances, export_csv_aquarists,
    export_csv_bap_genus, import_csv_species, import_csv_speciesInstances,
    import_csv_bap_genus
)
from species.asn_tools.asn_utils import (
    user_can_edit, user_can_edit_a, user_can_edit_s, user_can_edit_si,
    user_can_edit_srl, user_can_edit_sc, user_can_edit_sml, user_can_edit_club,
    user_is_club_member, user_is_pending_club_member,
    get_sml_collaborator_choices, get_sml_speciesInstance_choices,
    validate_sml_collection, get_sml_available_collaborators,
    get_sml_available_speciesInstances, sanitize_text, validate_url,
    processVideoURL
)
from species.asn_tools.asn_pdf_tools import generatePdfLabels

# Logger
logger = logging.getLogger(__name__)