"""
Shared utilities, imports, and base configuration for all views
"""

# Django core
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from django.core.validators import validate_email
from django.conf import settings
from django.utils.html import escape
from django.db.utils import IntegrityError
from django.core.mail import EmailMessage
from django.utils import timezone
from django.views.generic import ListView
#from django.views import View
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
    CaresRegistration, CaresApprover, SpeciesImportStaging,
    PageViewCount
)
from django.db.models import F

# Local forms
from species.forms import (
    UserProfileForm, UserProfileForm2, EmailAquaristForm, SpeciesForm, SpeciesInstanceForm,
    SpeciesCommentForm, SpeciesReferenceLinkForm, SpeciesForm2, CaresSpeciesForm, SpeciesInstanceForm2,
    CombinedSpeciesForm, SpeciesInstanceLogEntryForm, AquaristClubForm, AquaristClubForm2,
    AquaristClubMemberForm, AquaristClubMemberJoinForm, ImportCsvForm,
    SpeciesMaintenanceLogForm, SpeciesMaintenanceLogEntryForm,
    MaintenanceGroupCollaboratorForm, MaintenanceGroupSpeciesForm,
    SpeciesLabelsSelectionForm, SpeciesInstanceLabelFormSet,
    BapSubmissionForm, BapSubmissionFormEdit, BapSubmissionFormAdminEdit,
    BapGenusForm, BapSpeciesForm, BapSubmissionFilterForm,
    CaresRegistrationSubmitionAdminForm, CaresRegistrationApprovalForm, CaresApproverForm,
    CaresRegistrationAnonymousForm, CaresRegistrationAnonymousForm2, CaresRegistrationAdminForm, CaresSpeciesForm2
)

# Local utilities
from species.asn_tools.asn_img_tools import processUploadedImageFile, generate_qr_code

from species.asn_tools.asn_csv_tools import (
    export_csv_species, export_csv_speciesInstances, export_csv_aquarists,
    export_csv_aquaristClubs, export_csv_aquaristClubMembers,
    # CARES exports
    export_csv_caresRegistrations, export_csv_caresRegistrations_asn,
    export_csv_caresRegistrations_asn_pending, export_csv_caresRegistrations_cso,
    # CARES imports
    import_csv_caresRegistrations, #import_csv_caresRegistrations_cso,
    import_csv_species, import_csv_speciesInstances, import_csv_aquarist_clubs,
    export_csv_bap_genus, import_csv_bap_genus, export_csv_bap_submissions
)

from species.asn_tools.asn_utils import (
    user_can_edit, user_can_edit_a, user_can_edit_s, user_can_edit_si,
    user_can_edit_srl, user_can_edit_sc, user_can_edit_sml, user_can_edit_club,
    user_is_admin, user_is_club_member, user_is_pending_club_member,
    get_sml_collaborator_choices, get_sml_speciesInstance_choices,
    validate_sml_collection, get_sml_available_collaborators,
    get_sml_available_speciesInstances, sanitize_text, validate_url,
    processVideoURL, validate_normalize_instagram_url, validate_normalize_facebook_url,
    validate_normalize_youtube_url
)
from species.asn_tools.asn_pdf_tools import generatePdfLabels
from species.asn_tools.asn_cares_tools import get_matching_cares_approver
from species.asn_tools.asn_species_aggregation import collect_species_data_as_csv

# Logger
logger = logging.getLogger(__name__)


def record_page_view(page_type, object_id, is_authenticated):
    """
    Increment the PageViewCount for the given page_type + object_id + visitor_type.
    Uses get_or_create + F() expression update to avoid race conditions.
    Silently swallows any exception so a tracking failure never breaks a page load.
    """
    try:
        visitor_type = PageViewCount.VisitorType.AUTHENTICATED if is_authenticated else PageViewCount.VisitorType.ANONYMOUS
        obj, _ = PageViewCount.objects.get_or_create(
            page_type=page_type,
            object_id=object_id,
            visitor_type=visitor_type,
            defaults={'count': 0}
        )
        PageViewCount.objects.filter(pk=obj.pk).update(count=F('count') + 1)
    except Exception:
        logger.warning('record_page_view failed for page_type=%s object_id=%s', page_type, object_id, exc_info=True)