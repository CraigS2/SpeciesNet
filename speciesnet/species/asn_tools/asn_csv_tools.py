from species.models import Species, SpeciesInstance, AquaristClub, AquaristClubMember, BapGenus, ImportArchive, SpeciesImportStaging, SpeciesReferenceLink, User
from species.forms import SpeciesForm, SpeciesInstanceForm, CaresRegistration
from django.db import transaction
from django.db.models import FileField, Q
from django.db.models.functions import Lower
#from django.contrib.auth.models import User
from django.shortcuts import render
from django.views.generic.base import View
from django.http import HttpResponse
from django.core.files import File
from django.utils import timezone
from io import BytesIO
import csv
import datetime
import logging
from csv import DictReader
from io import StringIO, TextIOWrapper
from django.core.files.base import ContentFile
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from django.core.validators import URLValidator

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Field-level import rules for species staging import
# -------------------------------------------------------------------------

# Required CSV columns – rows missing these will be skipped with an error
SPECIES_IMPORT_REQUIRED_FIELDS = ['name', 'category', 'global_region']

# Default values applied when an optional enum cell is blank
SPECIES_IMPORT_ENUM_DEFAULTS = {
    'cares_family':         Species.CaresFamily.UNDEFINED,
    'iucn_red_list':        Species.IucnRedList.UNDEFINED,
    'cares_classification': Species.CaresStatus.NOT_CARES_SPECIES,
}

# Fields that are always overwritten on UPDATE (high-trust authoritative data)
SPECIES_ALWAYS_UPDATE_FIELDS = [
    'cares_classification',
    'cares_assessment_date',
    'iucn_red_list',
    'iucn_assessment_date',
    'cares_family',
    'global_region',
    'category',
]

# Fields written only when the existing value is blank/empty
SPECIES_UPDATE_IF_EMPTY_FIELDS = [
    'common_name',
    'alt_name',
    'description',
    'local_distribution',
]

# Fields that are never overwritten on UPDATE (managed locally)
SPECIES_NEVER_UPDATE_FIELDS: list = []

# All tracked species fields (used for change detection)
SPECIES_TRACKED_FIELDS = (
    SPECIES_ALWAYS_UPDATE_FIELDS
    + SPECIES_UPDATE_IF_EMPTY_FIELDS
    + SPECIES_NEVER_UPDATE_FIELDS
)

# Import Species List
# iterate through csv rows add only valid and non-duplicate species to DB

def import_csv_species (import_archive: ImportArchive, current_user: User):
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Species", "Import_Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one species per row
        row_count = 0
        import_count = 0
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            species_name = import_row['name']
            species_cares_classification = import_row['cares_classification']

            # validate Species data using Form validation
            species_form = SpeciesForm (import_row) # reads expected fields by header name
            if species_form.is_valid():
                species = species_form.save(commit=False)
                
                # validate input species name and verify non-duplicate
                if not Species.objects.filter(name=species_name).exists():
                    report_row = [species_name, "Validated: Species is unique and new, import successful"]
                    import_count = import_count + 1
                    newly_added_species = species_form.save()

                    # special case: re-importing previous species may have media images - try to restore them
                    species_image = import_row['species_image']
                    if species_image != '':
                        # seems like the following very simple 2 lines of code should happen via the species_form but it does not
                        newly_added_species.species_image = species_image
                        newly_added_species.save()

                    #special case: update bool 'render_cares' value if species is 'Not a CARES Species' ('NOTC')
                    if species_cares_classification != "NOTC":
                        species.render_cares = True
                        newly_added_species.save()
                else:
                    report_row = [species_name, "ERROR: species exists - cannot add duplicate species"]
            else:
                report_row = [species_name, "ERROR: validation failure - cannot save species"]
            csv_report_writer.writerow(report_row)

        # persist import report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.get_display_name + "_species_import_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)

        # persist import archive
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
        if import_count == 0:
            import_archive.import_status = ImportArchive.ImportStatus.FAIL
        else:
            if import_count == row_count:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
        import_archive.name = current_user.username + "_species_import"
        import_archive.save()
    return

# Import SpeciesInstance List
# iterate through csv rows verifying unique speciesInstances matching current user
# NOTE: users can have multiple instances of the same species assuming they vary in collection point or genetic traits

def import_csv_speciesInstances (import_archive: ImportArchive, current_user: User):
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Species Instance Name", "Import_Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one species per row
        row_count = 0
        import_count = 0
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            speciesInstance_user = import_row['aquarist']
            speciesInstance_name = import_row['name']

            # Note: current_user is of type django.utils.functional.SimpleLazyObject need a str type to compare with speciesInstance_user
            current_user_str = str(current_user)
            if (current_user_str == speciesInstance_user):

                # validate Species exists - required to instantiate SpeciesInstance
                species_name = import_row['species']
                if Species.objects.filter(name=species_name).exists():
                    species = Species.objects.get(name=species_name)

                    # validate pending SpeciesInstance object 
                    # will foreign key species resolve by name? TBD
                    
                    speciesInstance_form = SpeciesInstanceForm (import_row) # reads expected fields by header name
                    if speciesInstance_form.is_valid():
                        species_instance = speciesInstance_form.save(commit=False)
                        species_instance.species = species
                        species_instance.user = current_user

                        # validate instance is unique - not a duplicate - cannot rely on simply name: must use name, species name, and user
                        if not SpeciesInstance.objects.filter(name=speciesInstance_name, user=current_user).exists():
                            report_row = [speciesInstance_name, "Validated: species instance is unique and new for this user, import successful"]
                            import_count = import_count + 1
                            speciesInstance_form.save() # commits to DB
                        else:
                            report_row = [speciesInstance_name, "ERROR: species instance exists - cannot add duplicate"]
                    else:
                        report_row = [speciesInstance_name, "ERROR: validation failed - unable to create species instance"]
                            
                else:
                    report_row = [speciesInstance_name, "ERROR: species ", species_name, " does not exist - required for species instance"]
            else:
                report_row = [speciesInstance_name, "IGNORE: aquarist ", speciesInstance_user, " is not the active user: ", current_user]
            csv_report_writer.writerow(report_row)


        # persist import report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.get_display_name + "_species_instance_import_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)

        # persist import archive
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
        if import_count == 0:
            import_archive.import_status = ImportArchive.ImportStatus.FAIL
        else:
            if import_count == row_count:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
        import_archive.name = current_user.username + "_speciesInstance_import"
        import_archive.save()
    return


# Import Aquarist Clubs from csv
# iterate through csv rows check if club exists, and create if it does not yet exist in the db. 

def import_csv_aquarist_clubs (import_archive: ImportArchive, current_user: User, aquarist_club: AquaristClub):
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Genus", "Import_Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one genus per row
        row_count = 0
        import_count = 0
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            club_name = import_row['name']

            if AquaristClub.objects.filter(name=club_name).exists():
                print ('Aquarist Club import skipping row ' + str(row_count) + ': Club exists (' + club_name + ')')
            else:
                # create club
                print ('Aquarist Club import started for row ' + str(row_count))
                club = AquaristClub()
                club.name = club_name
                club.acronym = import_row['acronym']
                club.about = import_row['about']
                club.logo_image = import_row['logo_image']
                club.website = import_row['website']
                club.city = import_row['city']
                club.state = import_row['state']
                club.country = import_row['country']
                club.require_member_approval = import_row['require_member_approval']
                club.bap_guidelines = import_row['bap_guidelines']
                club.bap_notes_template = import_row['bap_notes_template']
                club.bap_default_points = import_row['bap_default_points']
                club.cares_muliplier = import_row['cares_muliplier']
                club.bap_start_date = import_row['bap_start_date']
                club.bap_end_date = import_row['bap_end_date']
                club.is_bap_club = import_row['is_bap_club']
                club.is_cares_club = import_row['is_cares_club']   

                club.save() 

                print ('  Club ' + club.acronym + ' successfully added to db.')
                logger.info ('User %s imported AquaristClub: %s (%s)', current_user.username, club.acronym, club.name)
                status_txt = 'SUCCESS: New ' + club.acronym + ' Aquarist Club added (' + club.name + ')'
                report_row = [club_name, status_txt] 

                csv_report_writer.writerow(report_row)

        # persist import report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.username + '_' + bap_club.acronym + "_club_import_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)

        # persist import archive
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
        if import_count == 0:
            import_archive.import_status = ImportArchive.ImportStatus.FAIL
        else:
            if import_count == row_count:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
        import_archive.name = current_user.username + '_' + club.acronym + '_club_import'
        import_archive.save()
    return



# Import BAP Genus List
# iterate through csv rows check if example species exists, and add or update BAP Genus entries. Supports club import/update workflow

def import_csv_bap_genus (import_archive: ImportArchive, current_user: User, bap_club: AquaristClub):
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Genus", "Import_Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one genus per row
        row_count = 0
        import_count = 0
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            genus_name = import_row['name']
            bap_points = int(import_row['points'])
            example_species_name = import_row['example_species']
            
            print ('BAP Points import started for row ' + str(row_count))

            if BapGenus.objects.filter(club=bap_club, name=genus_name).exists():
                print ('  Genus exists: ' + genus_name)
                try:
                    bap_genus = BapGenus.objects.get(club=bap_club, name=genus_name)
                    
                    print ('  Points comparison current value: ' + str(bap_genus.points) + ' and new value: ' + str(bap_points))

                    if (bap_points != bap_genus.points):
                        bap_genus.points = bap_points        # no other update needed
                        bap_genus.save()

                        print ('  BAP Points updated for ' + genus_name + ': ' + (str(bap_genus.points)))

                        logger.info ('User %s imported BapGenus list for club %s: Genus points updated for: %s.', current_user.username, bap_club.acronym, genus_name)
                        status_txt = 'SUCCESS: ' + bap_club.acronym + ' BapGenus points updated for ' + genus_name + ': ' + str(bap_genus.points)
                        report_row = [genus_name, status_txt]                       
                        import_count = import_count + 1
                    else:
                        print ('  BAP Points not updated they are the same for ' + genus_name + ': ' + (str(bap_points)))

                        logger.info ('User %s imported BapGenus list for club %s: Genus points unchanged for: %s.', current_user.username, bap_club.acronym, genus_name)
                        status_txt = 'VERIFIED: ' + bap_club.acronym + ' BapGenus import points match existing points for : ' + genus_name
                        report_row = [genus_name, status_txt]                       
                except ObjectDoesNotExist:
                    report_row = [genus_name, ""]
                    status_txt = 'ERROR: ' + bap_club.acronym + ' BapGenus lookup exception - object does not exist for: ' + genus_name
                    report_row = [genus_name, status_txt]                       
                    logger.error ('User %s importing BapGenus list for club %s: BapGenus lookup error for genus: %s.', current_user.username, bap_club.acronym, genus_name)
                except MultipleObjectsReturned:
                    status_txt = 'ERROR: ' + bap_club.acronym + ' BapGenus lookup exception - multiple objects found for: ' + genus_name
                    report_row = [genus_name, status_txt]                       
                    logger.error ('User %s importing BapGenus list for club %s: BapGenus lookup multiple objects found for genus: %s.', current_user.username, bap_club.acronym, genus_name)
            else: 
                
                print ('  BapGenus points not found for ' + genus_name + ' adding and setting points value: ' + str(bap_points))

                bap_genus = BapGenus()
                bap_genus.name = genus_name
                bap_genus.points = bap_points
                bap_genus.club = bap_club
                
                # set current species count for genus - will be zero but may be non-zero if species got added after BapGenus initialization

                genus_species = Species.objects.filter(name__regex=r'^' + genus_name + r'\s')          # TODO optimize remove N+1 query
                bap_genus.species_count = len(genus_species)  
                print ('  BapGenus added: ' + bap_genus.name + ' current species count: ' + str(bap_genus.species_count))       
                bap_genus.species_override_count = 0

                # now see if example species exists - add it if it does not

                print ('  BapGenus added now checking to see if example species exists or needs to be added: ' + example_species_name)

                try:
                    print ('  BapGenus import - query on example species: ' + example_species_name )
                    example_species = Species.objects.get(name=example_species_name)
                    bap_genus.example_species = example_species
                    import_count = import_count + 1
                    bap_genus.save()

                    print ('  BapGenus import - example_species found: ' + example_species.name )
                    logger.info ('User %s imported BapGenus for club %s new BapGenus entry with example species found: %s.', current_user.username, bap_club.acronym, example_species_name )
                    status_txt = 'SUCCESS: New ' + bap_club.acronym + ' BapGenus added with example species found: ' + example_species_name
                    report_row = [genus_name, status_txt]                       

                except ObjectDoesNotExist:
                    print ('  BapGenus import - example_species not found - adding: ' + example_species_name )
                    example_species = Species()
                    example_species.name = example_species_name
                    example_species.category = import_row['category']
                    example_species.global_region = import_row['global_region']
                    example_species.description = import_row['description']
                    example_species.save()

                    bap_genus.example_species = example_species
                    bap_genus.species_count = bap_genus.species_count + 1
                    import_count = import_count + 1  
                    bap_genus.save()

                    logger.info ('User %s imported BapGenus for club %s new BapGenus entry with example species added: %s.', current_user.username, bap_club.acronym, example_species_name )
                    status_txt = 'SUCCESS: New ' + bap_club.acronym + ' BapGenus added with example species: ' + example_species_name
                    report_row = [genus_name, status_txt]                                              
                except MultipleObjectsReturned:
                    report_row = [genus_name, "ERROR: BapGenus example_species failed to import: ", example_species_name]
                    logger.error ('User %s importing BapGenus for club %s: BapGenus add example_species multiple objects found for: %s.', current_user.username, bap_club.acronym, example_species_name)
                
                bap_genus.save()
                
                print ('  BapGenus added finished processing Genus : ' + genus_name)
                
            csv_report_writer.writerow(report_row)

        # persist import report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.username + '_' + bap_club.acronym + "_bap_genus_import_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)

        # persist import archive
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
        if import_count == 0:
            import_archive.import_status = ImportArchive.ImportStatus.FAIL
        else:
            if import_count == row_count:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
        import_archive.name = current_user.username + '_' + bap_club.acronym + '_species_import'
        import_archive.save()
    return


# Import Species Reference Links from CSV
# Iterate through CSV rows, look up each species by name (case-insensitive exact match),
# validate the reference URL and name_prefix, then create and save a SpeciesReferenceLink.

def import_csv_species_reference_links(import_archive: ImportArchive, current_user: User) -> dict:
    """
    Process a CSV file to import SpeciesReferenceLink objects.
    Expected CSV columns: species, reference_url, name_prefix
    Returns a summary dict with keys:
        success_count  - number of rows imported successfully
        error_count    - number of rows that failed
        errors         - list of (row_number, species_value, error_message) tuples
    """
    url_validator = URLValidator(schemes=['http', 'https'])

    # Prepare results CSV report for archiving
    csv_report_buffer = StringIO()
    csv_report_writer = csv.writer(csv_report_buffer)
    csv_report_writer.writerow(['Row', 'Species', 'Import_Status'])

    row_count = 0
    success_count = 0
    errors = []

    with open(import_archive.import_csv_file.path, 'r', encoding='utf-8') as import_file:
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            raw_species_name = import_row.get('species', '')
            species_name = raw_species_name.strip()
            print ('CSV Reference Link Import Species: ' + species_name)

            try:
                matched_species = Species.objects.get(name__iexact=species_name)
                print ('CSV Reference Link Import Species Match: ' + matched_species.name)

            except ObjectDoesNotExist:
                error_message = f'Species not found: "{species_name}"'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.warning(
                    'User %s importing species reference links row %d: %s',
                    current_user.username, row_count, error_message,
                )
                continue
            except MultipleObjectsReturned:
                error_message = f'Multiple species found for name: "{species_name}"'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.warning(
                    'User %s importing species reference links row %d: %s',
                    current_user.username, row_count, error_message,
                )
                continue

            raw_reference_url = import_row.get('reference_url', '')
            reference_url = raw_reference_url.strip()
            print ('CSV Reference Link Import Reference Link: ' + reference_url)

            try:
                url_validator(reference_url)
                print ('CSV Reference Link Import Reference Link Validated: ' + reference_url)
            except ValidationError as validation_error:
                error_message = f'Invalid reference URL: "{reference_url}" – {validation_error.message}'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.warning(
                    'User %s importing species reference links row %d: %s',
                    current_user.username, row_count, error_message,
                )
                continue

            raw_name_prefix = import_row.get('name_prefix', '')
            name_prefix = raw_name_prefix.strip()
            print ('CSV Reference Link Import Previx: ' + name_prefix)

            if not name_prefix:
                error_message = 'name_prefix is empty or missing'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.warning(
                    'User %s importing species reference links row %d species "%s": %s',
                    current_user.username, row_count, species_name, error_message,
                )
                continue

            reference_link_name = name_prefix + ': ' + matched_species.name

            # Check for duplicates using database queries (more efficient than loading all links)
            if SpeciesReferenceLink.objects.filter(species=matched_species, name=reference_link_name).exists():
                error_message = f'Duplicate name: "{reference_link_name}" already exists'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.warning(
                    'User %s importing species reference links row %d species "%s": %s',
                    current_user.username, row_count, species_name, error_message,
                )
                continue

            if SpeciesReferenceLink.objects.filter(species=matched_species, reference_url=reference_url).exists():
                error_message = f'Duplicate URL: "{reference_url}" already exists for this species'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.warning(
                    'User %s importing species reference links row %d species "%s": %s',
                    current_user.username, row_count, species_name, error_message,
                )
                continue

            new_reference_link = SpeciesReferenceLink()
            new_reference_link.species = matched_species
            new_reference_link.user = current_user
            new_reference_link.reference_url = reference_url
            new_reference_link.name = reference_link_name

            try:
                new_reference_link.save()
                success_count = success_count + 1
                csv_report_writer.writerow([row_count, species_name, f'SUCCESS: Created "{reference_link_name}"'])
                logger.info(
                    'User %s imported species reference link row %d: "%s"',
                    current_user.username, row_count, reference_link_name,
                )
                print ('CSV Reference Link Import Success: ' + reference_link_name)

            except Exception as save_error:
                error_message = f'Save failed: {str(save_error)}'
                errors.append((row_count, species_name, error_message))
                csv_report_writer.writerow([row_count, species_name, f'ERROR: {error_message}'])
                logger.error(
                    'User %s importing species reference links row %d species "%s": %s',
                    current_user.username, row_count, species_name, error_message,
                )

    csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
    csv_report_filename = current_user.username + '_species_reference_link_import_log.csv'
    import_archive.import_results_file.save(csv_report_filename, csv_report_file)

    error_count = len(errors)
    if success_count == 0:
        import_archive.import_status = ImportArchive.ImportStatus.FAIL
    elif error_count > 0:
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
    else:
        import_archive.import_status = ImportArchive.ImportStatus.FULL

    import_archive.name = current_user.username + '_species_reference_link_import'
    import_archive.save()

    return {
        'success_count': success_count,
        'error_count': error_count,
        'errors': errors,
    }


#Export Species List, SpeciesInstances, Aquarists, Clubs, BAP

def export_csv_bap_genus(bap_club: AquaristClub):
    bapGenusSet = BapGenus.objects.filter(club=bap_club)
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bap_genus_points_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(['club', 'name', 'points', 'category', 'global_region', 'example_species', 'example_species_description'])
    for bapGenus in bapGenusSet:
        if bapGenus.example_species:
            writer.writerow([bapGenus.club.acronym, bapGenus.name, bapGenus.points, bapGenus.example_species.category, bapGenus.example_species.global_region, 
                            bapGenus.example_species.name, bapGenus.example_species.description])
        else:
            logger.error ('BAP Export error for club %s: BapGenus %s. has null example_species', bap_club.acronym, bapGenus.name)
    return response


def export_csv_aquarists():
    aquaristSet = User.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aquarists_export.csv"'},
    )
    writer = csv.writer(response)

    writer.writerow([
       # id    username    email    first_name    last_name    state    country
        'id', 'username', 'email', 'first_name', 'last_name', 'state', 'country', 
       # is_private_name    is_private_email    is_email_blocked   is_private_location    date_joined
        'is_private_name', 'is_private_email', 'is_email_blocked', 'is_private_location', 'date_joined', 
       # is_admin    is_staff    is_species_admin    is_proxy   is_active 
        'is_admin', 'is_staff', 'is_species_admin', 'is_proxy' 'is_active',
       # instagram_url    facebook_url    youtube_url    prefer_tile_view
        'instagram_url', 'facebook_url', 'youtube_url', 'prefer_tile_view'
        ])
    
    for user in aquaristSet:
        writer.writerow([
            #    id       username       email       first_name       last_name       state       country
            user.id, user.username, user.email, user.first_name, user.last_name, user.state, user.country, 
            #    is_private_name       is_private_email       is_email_blocked       is_private_location       date_joined
            user.is_private_name, user.is_private_email, user.is_email_blocked, user.is_private_location, user.date_joined, 
            #    is_admin       is_staff       is_species_admin      is_proxy        is_active 
            user.is_admin, user.is_staff, user.is_species_admin, user.is_proxy, user.is_active,
            #    instagram_url       facebook_url       youtube_url       prefer_tile_view
            user.instagram_url, user.facebook_url, user.youtube_url, user.prefer_tile_view
            ])
        
    return response

def export_csv_species():
    speciesSet = Species.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="species_export.csv"'},
    )
    writer = csv.writer(response)

    writer.writerow([
       # id    name   alt_name    common_name     description    species_image    photo_credit           
        'id', 'name', 'alt_name', 'common_name', 'description', 'species_image', 'photo_credit', 
       # category    global_region    local_distribution 
        'category', 'global_region', 'local_distribution', 
       # cares_family            cares_classification     cares_assessment_date     iucn_red_list   iucn_assessment_date    
        'cares_family',         'cares_classification',  'cares_assessment_date',  'iucn_red_list', 'iucn_assessment_date', 
       # created   created_by     lastUpdated    last_edited_by    
        'created', 'created_by', 'lastUpdated', 'last_edited_by' 
        ])
    
    for species in speciesSet:
        writer.writerow([
            #       id          name          alt_name          common_name          description          species_image          photo_credit           
            species.id, species.name, species.alt_name, species.common_name, species.description, species.species_image, species.photo_credit, 
            #       category          global_region          local_distribution 
            species.category, species.global_region, species.local_distribution, 
            #       cares_family          cares_classification          cares_assessment_date          iucn_red_list          iucn_assessment_date    
            species.cares_family, species.cares_classification, species.cares_assessment_date, species.iucn_red_list, species.iucn_assessment_date,
            #       created          created_by          lastUpdated          last_edited_by    
            species.created, species.created_by, species.lastUpdated, species.last_edited_by
            ])
    
    return response

def export_csv_speciesInstances():
    speciesInstances = SpeciesInstance.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="species_instance_export.csv"'},
    )
    writer = csv.writer(response)

    writer.writerow([
       # id    user    name    species    unique_traits    genetic_traits    collection_point
        'id' ,'user', 'name', 'species', 'unique_traits', 'genetic_traits', 'collection_point', 
       # acquired_from    year_acquired    aquarist_species_image aquarist_species_video_url 
        'acquired_from', 'year_acquired', 'aquarist_species_image', 'aquarist_species_video_url', 
       # aquarist_notes    have_spawned    spawning_notes    have_reared_fry    fry_rearing_notes    young_available    young_available_image 
        'aquarist_notes', 'have_spawned', 'spawning_notes', 'have_reared_fry', 'fry_rearing_notes', 'young_available', 'young_available_image', 
       # currently_keep    enable_species_log    log_is_private    cares_registered    created    lastUpdated           
        'currently_keep', 'enable_species_log', 'log_is_private', 'cares_registered', 'created', 'lastUpdated'
        ])
    for si in speciesInstances:
        writer.writerow([
            #  id     user              name     species     unique_traits     genetic_traits     collection_point
            si.id, si.user.username, si.name, si.species, si.unique_traits, si.genetic_traits, si.collection_point, 
            #  acquired_from     year_acquired     aquarist_species_image     aquarist_species_video_url 
            si.acquired_from, si.year_acquired, si.aquarist_species_image, si.aquarist_species_video_url, 
            #  aquarist_notes     have_spawned     spawning_notes     have_reared_fry     fry_rearing_notes     young_available     young_available_image 
            si.aquarist_notes, si.have_spawned, si.spawning_notes, si.have_reared_fry, si.fry_rearing_notes, si.young_available, si.young_available_image,
            # currently_keep      enable_species_log     log_is_private     cares_registered     created     lastUpdated           
            si.currently_keep, si.enable_species_log, si.log_is_private, si.cares_registered, si.created, si.lastUpdated
        ])

    return response

def export_csv_aquaristClubs():
    clubs = AquaristClub.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aquarist_club_export.csv"'},
    )
    writer = csv.writer(response)

    writer.writerow([
       # id     name    acronym    about    logo_image    website    city    state    country   
        'id' , 'name', 'acronym', 'about', 'logo_image', 'website', 'city', 'state', 'country',
       # bap_guidelines    bap_notes_template    cares_muliplier    bap_start_date    bap_end_date
        'bap_guidelines', 'bap_notes_template', 'cares_muliplier', 'bap_start_date', 'bap_end_date',
       # is_bap_club is_cares_club require_member_approval created lastUpdated            
        'is_bap_club', 'is_cares_club', 'require_member_approval', 'created', 'lastUpdated'
        ])
    for club in clubs:
        writer.writerow([
            #    id       name        acronym      about       logo_image       website       city       state       country   
            club.id, club.name, club.acronym, club.about, club.logo_image, club.website, club.city, club.state, club.country,
            #    bap_guidelines       bap_notes_template       cares_muliplier       bap_start_date       bap_end_date
            club.bap_guidelines, club.bap_notes_template, club.cares_muliplier, club.bap_start_date, club.bap_end_date,
            #    is_bap_club       is_cares_club       require_member_approval       created       lastUpdated            
            club.is_bap_club, club.is_cares_club, club.require_member_approval, club.created, club.lastUpdated
        ])

    return response

def export_csv_aquaristClubMembers():
    club_members = AquaristClubMember.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aquarist_club_member_export.csv"'},
    )
    writer = csv.writer(response)
     
    writer.writerow([
       # id  name club user membership_approved   
        'id', 'name', 'club', 'user', 'membership_approved',
       # bap_participant is_club_admin is_cares_admin 
        'bap_participant', 'is_club_admin', 'is_cares_admin',
       # date_requested last_updated 
        'date_requested', 'last_updated'
        ])
    for cm in club_members:
        writer.writerow([
            # id  name club user membership_approved   
            cm.id, cm.name, cm.club, cm.user, cm.membership_approved, 
            # bap_participant is_club_admin is_cares_admin 
            cm.bap_participant, cm.is_club_admin, cm.is_cares_admin, 
            # date_requested last_updated 
            cm.date_requested, cm.last_updated
        ])

    return response


def export_csv_bap_submissions():
    bap_submissions = BapSubmission.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aquarist_club_member_export.csv"'},
    )

    writer = csv.writer(response)
    writer.writerow([
        # name   club    year    speciesInstance
        'name', 'club', 'year', 'speciesInstance',
        # status   points    request_points_review    notes
        'status', 'points', 'request_points_review', 'notes',
        # breeder_comments    admin_comments  active  created lastUpdated
        'breeder_comments', 'admin_comments', 'active', 'created', 'lastUpdated'
        ])
    for bap_s in bap_submissions:
        writer.writerow([
            # name  aquarist   year speciesInstance
            bap_s.name, bap_s.aquarist, bap_s.year, bap_s.speciesInstance,
            #     status        points        request_points_review         notes
            bap_s.status, bap_s.points, bap_s.request_points_review, bap_s.notes,
            # breeder_comments    admin_comments  active  created lastUpdated
            bap_s.breeder_comments, bap_s.admin_comments, bap_s.active, bap_s.created, bap_s.lastUpdated
        ])

    return response


def export_csv_caresRegistrations():
    registrations = CaresRegistration.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cares_registration_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow([
       # id name aquarist_name aquarist_email affiliate_club species collection_location
        'id' , 'name', 'aquarist_name', 'aquarist_email', 'affiliate_club', 'species', 'collection_location',
       # species_source year_acquired verification_photo species_has_spawned young_available offspring_shared
        'species_source', 'year_acquired', 'verification_photo', 'species_has_spawned', 'young_available', 'offspring_shared',
       # cares_approver approver_notes status          
        'cares_approver', 'approver_notes', 'status',
       # date_requested lastUpdated last_updated_by last_report_date
        'date_requested', 'lastUpdated', 'last_updated_by', 'last_report_date'
        ])
    for reg in registrations:
        writer.writerow([
            # id name aquarist_name aquarist_email affiliate_club species collection_location
            reg.id, reg.name, reg.aquarist_name, reg.aquarist_email, reg.affiliate_club, reg.species, reg.collection_location,
            # species_source year_acquired verification_photo species_has_spawned young_available offspring_shared
            reg.species_source, reg.year_acquired, reg.verification_photo, reg.species_has_spawned, reg.young_available, reg.offspring_shared,
            # cares_approver approver_notes status          
            reg.cares_approver, reg.approver_notes, reg.status,
            # date_requested lastUpdated last_updated_by last_report_date
            reg.date_requested, reg.lastUpdated, reg.last_updated_by, reg.last_report_date
        ])

    return response


# ---------------------------------------------------------------------------
# CARES Species Import – Phase 2: Staging and Commit
# ---------------------------------------------------------------------------

# DateField names on Species that are stored as text in SpeciesImportStaging.
# These require explicit string→date conversion when committing to the Species table.
SPECIES_DATE_FIELDS = {'cares_assessment_date', 'iucn_assessment_date'}


def _parse_date(value: str) -> 'datetime.date | None':
    """Convert a *yyyy-mm-dd* string to a :class:`datetime.date`.

    Returns ``None`` if *value* is blank, ``None``, or not a valid ISO date.
    """
    if not value or not value.strip():
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except (ValueError, TypeError):
        logger.warning('Species import: could not parse date value %r', value)
        return None


def _find_existing_species(name: str):
    """Return an existing Species record matching *name* (case-insensitive) or None."""
    print ('Species Import - Lookup of existing species: ' + name)
    try:
        return Species.objects.get(name__iexact=name)
    except Species.DoesNotExist:
        pass
    # Alternate name match
    try:
        return Species.objects.get(alt_name__iexact=name)
    except (Species.DoesNotExist, Species.MultipleObjectsReturned):
        pass
    return None


def _build_changed_fields(existing_species: Species, import_row: dict) -> dict:
    """
    Compare *import_row* values against *existing_species* and return a dict
    of changed fields:  {'field': {'old': old_val, 'new': new_val}}
    """
    field_map = {
        'cares_family':          'cares_family',
        'cares_assessment_date': 'cares_assessment_date',
        'cares_classification':  'cares_classification',
        'iucn_red_list':         'iucn_red_list',
        'iucn_assessment_date':  'iucn_assessment_date',        
        'global_region':         'global_region',
        'category':              'category',
        'common_name':           'common_name',
        'alt_name':              'alt_name',
        'description':           'description',
        'local_distribution':    'local_distribution',
    }
    changed = {}
    for csv_field, model_field in field_map.items():
        new_val = import_row.get(csv_field, '')
        old_val = str(getattr(existing_species, model_field, '') or '')
        if new_val != old_val:
            changed[csv_field] = {'old': old_val, 'new': new_val}
    return changed


def import_csv_species_to_staging(import_archive: ImportArchive, current_user: User) -> dict:
    """
    Parse a species CSV and create SpeciesImportStaging records for review.

    Required CSV columns: name, category, global_region
    Optional columns (blank cells use defaults):
      - alt_name, common_name, description, local_distribution  → blank string
      - cares_family          → UDF (Undefined)
      - iucn_red_list         → UN  (Undefined)
      - cares_classification  → NOTC (Not a CARES Species)

    Returns a summary dict with counts: new, update, skip, conflict, error.
    """
    summary = {'new': 0, 'update': 0, 'skip': 0, 'conflict': 0, 'error': 0, 'total': 0}

    with open(import_archive.import_csv_file.path, 'r', encoding='utf-8') as import_file:
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        csv_report_writer.writerow(['Row', 'Species', 'Action', 'Review_Status', 'Changed_Fields', 'Notes'])

        row_number = 0
        for import_row in DictReader(import_file):
            row_number += 1
            summary['total'] += 1
            species_name = import_row.get('name', '').strip()
            notes = ''

            # Validate required fields
            missing = [f for f in SPECIES_IMPORT_REQUIRED_FIELDS if not import_row.get(f, '').strip()]
            if missing or not species_name:
                all_missing = (['name'] if not species_name else []) + [f for f in missing if f != 'name']
                notes = f'Missing required field(s): {", ".join(all_missing)}'
                logger.warning('Species staging row %d skipped: %s', row_number, notes)
                summary['error'] += 1
                csv_report_writer.writerow([row_number, species_name, 'ERROR', 'N/A', '', notes])
                continue

            # Apply defaults for optional enum fields when cell is blank
            for field, default in SPECIES_IMPORT_ENUM_DEFAULTS.items():
                if not import_row.get(field, '').strip():
                    import_row[field] = default

            existing = _find_existing_species(species_name)

            if existing is None:
                # New species
                action = SpeciesImportStaging.ImportAction.NEW
                changed_fields = {}
                summary['new'] += 1
            else:
                changed_fields = _build_changed_fields(existing, import_row)
                if not changed_fields:
                    action = SpeciesImportStaging.ImportAction.SKIP
                    summary['skip'] += 1
                else:
                    # Determine if any change is a potential conflict (non-empty to non-empty)
                    has_conflict = any(
                        v['old'] and v['new'] and v['old'] != v['new']
                        for v in changed_fields.values()
                    )
                    action = SpeciesImportStaging.ImportAction.CONFLICT if has_conflict else SpeciesImportStaging.ImportAction.UPDATE
                    if action == SpeciesImportStaging.ImportAction.CONFLICT:
                        summary['conflict'] += 1
                    else:
                        summary['update'] += 1

            staging = SpeciesImportStaging(
                import_archive=import_archive,
                import_row_number=row_number,
                action=action,
                existing_species=existing,
                new_name=species_name,
                new_alt_name=import_row.get('alt_name', ''),
                new_common_name=import_row.get('common_name', ''),
                new_description=import_row.get('description', ''),
                new_category=import_row.get('category', ''),
                new_global_region=import_row.get('global_region', ''),
                new_local_distribution=import_row.get('local_distribution', ''),
                new_cares_family=import_row.get('cares_family', ''),
                new_cares_classification=import_row.get('cares_classification', ''),
                new_cares_assessment_date=import_row.get('cares_assessment_date', ''),
                new_iucn_red_list=import_row.get('iucn_red_list', ''),
                new_iucn_assessment_date=import_row.get('iucn_assessment_date', ''),
                changed_fields=changed_fields,
                review_status=SpeciesImportStaging.ReviewStatus.PENDING,
            )
            staging.save()

            changed_fields_str = ', '.join(changed_fields.keys()) if changed_fields else ''
            csv_report_writer.writerow([row_number, species_name, action, 'PENDING', changed_fields_str, notes])

    # Persist import summary report
    csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
    csv_report_filename = f"{current_user.username}_cares_species_staging_log.csv"
    import_archive.import_results_file.save(csv_report_filename, csv_report_file)

    # Update import archive status
    if summary['error'] > 0 and (summary['new'] + summary['update'] + summary['skip'] + summary['conflict']) == 0:
        import_archive.import_status = ImportArchive.ImportStatus.FAIL
    elif summary['error'] > 0:
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
    else:
        import_archive.import_status = ImportArchive.ImportStatus.FULL
    import_archive.name = f"{current_user.username}_cares_species_staging"
    import_archive.save()

    logger.info('CARES species staging import complete: %s', summary)
    return summary


def commit_species_import_staging(import_archive: ImportArchive, current_user: User) -> dict:
    """
    Commit all APPROVED staging records for *import_archive* to the Species table.

    Respects field-level import rules:
    - SPECIES_ALWAYS_UPDATE_FIELDS: always written on UPDATE
    - SPECIES_UPDATE_IF_EMPTY_FIELDS: written only when existing value is blank
    - SPECIES_NEVER_UPDATE_FIELDS: never written on UPDATE

    Returns a results dict with counts: added, updated, skipped, errors.
    """
    results = {'added': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'total': 0}

    approved_records = SpeciesImportStaging.objects.filter(
        import_archive=import_archive,
        review_status__in=[
            SpeciesImportStaging.ReviewStatus.APPROVED,
            SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE,
        ],
    ).select_related('existing_species')

    csv_report_buffer = StringIO()
    csv_report_writer = csv.writer(csv_report_buffer)
    csv_report_writer.writerow(['Row', 'Species', 'Action', 'Result', 'Notes'])

    with transaction.atomic():
        for staged_changes in approved_records:
            results['total'] += 1
            try:
                if staged_changes.action == SpeciesImportStaging.ImportAction.NEW:
                    logger.info('Species import saving staged changes to NEW species: %s', staged_changes.new_name)

                    species = Species(
                        name=staged_changes.new_name,
                        alt_name=staged_changes.new_alt_name,
                        common_name=staged_changes.new_common_name,
                        description=staged_changes.new_description,
                        local_distribution=staged_changes.new_local_distribution,
                        cares_family=staged_changes.new_cares_family or Species.CaresFamily.UNDEFINED,
                        cares_classification=staged_changes.new_cares_classification or Species.CaresStatus.NOT_CARES_SPECIES,
                        cares_assessment_date=_parse_date(staged_changes.new_cares_assessment_date),
                        iucn_red_list=staged_changes.new_iucn_red_list or Species.IucnRedList.UNDEFINED,
                        iucn_assessment_date=_parse_date(staged_changes.new_iucn_assessment_date),
                        category=staged_changes.new_category or Species.Category.CICHLIDS,
                        global_region=staged_changes.new_global_region or Species.GlobalRegion.AFRICA,
                        created_by=current_user,
                        last_edited_by=current_user,
                    )
                    species.render_cares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
                    print ('Committing Species: ' + staged_changes.new_name)
                    species.save()
                    staged_changes.existing_species = species
                    results['added'] += 1
                    csv_report_writer.writerow([staged_changes.import_row_number, staged_changes.new_name, 'NEW', 'Added', ''])

                elif staged_changes.action in (SpeciesImportStaging.ImportAction.UPDATE, SpeciesImportStaging.ImportAction.CONFLICT):
                    species = staged_changes.existing_species
                    logger.info('Species import saving staged changes to existing species: %s', species.name)

                    if species is None:
                        raise ObjectDoesNotExist(f"existing_species is None for staging pk={staged_changes.pk}")

                    new_vals = {
                        'cares_classification':  staged_changes.new_cares_classification,
                        'cares_family':          staged_changes.new_cares_family,
                        'cares_assessment_date': staged_changes.new_cares_assessment_date,
                        'iucn_red_list':         staged_changes.new_iucn_red_list,
                        'iucn_assessment_date':  staged_changes.new_iucn_assessment_date,
                        'global_region':         staged_changes.new_global_region,
                        'category':              staged_changes.new_category,
                        'common_name':           staged_changes.new_common_name,
                        'alt_name':              staged_changes.new_alt_name,
                        'description':           staged_changes.new_description,
                        'local_distribution':    staged_changes.new_local_distribution,
                    }

                    updated_fields_list = []
                    is_override = staged_changes.review_status == SpeciesImportStaging.ReviewStatus.APPROVED_OVERRIDE

                    if is_override:
                        # APPROVED_OVERRIDE: force-write every field that was detected as changed.
                        for field, vals in staged_changes.changed_fields.items():
                            new_val = vals.get('new')
                            if new_val is None:
                                continue
                            if field in SPECIES_DATE_FIELDS:
                                setattr(species, field, _parse_date(new_val))
                                updated_fields_list.append(field)
                            elif new_val != '':
                                setattr(species, field, new_val)
                                updated_fields_list.append(field)
                    else:
                        # APPROVED: respect the standard field-level update rules.
                        for field in SPECIES_ALWAYS_UPDATE_FIELDS:
                            new_val = new_vals.get(field)
                            if field in SPECIES_DATE_FIELDS:
                                if new_val:
                                    setattr(species, field, _parse_date(new_val))
                                    updated_fields_list.append(field)
                            elif new_val is not None and new_val != '':
                                setattr(species, field, new_val)
                                updated_fields_list.append(field)
                        for field in SPECIES_UPDATE_IF_EMPTY_FIELDS:
                            new_val = new_vals.get(field)
                            if new_val is not None and new_val != '' and not getattr(species, field, ''):
                                setattr(species, field, new_val)
                                updated_fields_list.append(field)
                        # SPECIES_NEVER_UPDATE_FIELDS are intentionally skipped

                    species.render_cares = species.cares_classification != Species.CaresStatus.NOT_CARES_SPECIES
                    species.last_edited_by = current_user
                    species.save()
                    results['updated'] += 1
                    csv_report_writer.writerow([
                        staged_changes.import_row_number, staged_changes.new_name, staged_changes.action,
                        'Updated', f"fields: {', '.join(updated_fields_list)}"
                    ])

                else:
                    # SKIP action – shouldn't normally be APPROVED, but handle gracefully
                    results['skipped'] += 1
                    csv_report_writer.writerow([staged_changes.import_row_number, staged_changes.new_name, staged_changes.action, 'Skipped', ''])

                # Update staging record's reviewed_at timestamp
                staged_changes.reviewed_at = timezone.now()
                staged_changes.save(update_fields=['existing_species', 'reviewed_at'])

            except Exception as exc:
                logger.error('Error committing staging pk=%s: %s', staged_changes.pk, exc, exc_info=True)
                results['errors'] += 1
                csv_report_writer.writerow([staged_changes.import_row_number, staged_changes.new_name, staged_changes.action, 'ERROR', str(exc)])

    # Persist commit report
    csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
    csv_report_filename = f"{current_user.username}_cares_species_commit_log.csv"
    import_archive.import_results_file.save(csv_report_filename, csv_report_file, save=False)

    if results['errors'] > 0 and results['added'] + results['updated'] == 0:
        import_archive.import_status = ImportArchive.ImportStatus.FAIL
    elif results['errors'] > 0:
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
    else:
        import_archive.import_status = ImportArchive.ImportStatus.FULL
    import_archive.save()

    logger.info('CARES species commit complete: %s', results)
    return results