from species.models import Species, SpeciesInstance, ImportArchive, User
from species.forms import SpeciesForm, SpeciesInstanceForm
from django.db.models import FileField
#from django.contrib.auth.models import User
from django.shortcuts import render
from django.views.generic.base import View
from django.http import HttpResponse
from django.core.files import File
from io import BytesIO
import csv
from csv import DictReader
from io import StringIO, TextIOWrapper
from django.core.files.base import ContentFile

# Import Species List
# iterate through csv rows add only valid and non-duplicate species to DB

def import_csv_species (import_archive: ImportArchive, current_user: User):
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Species", "Import Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one species per row
        row_count = 0
        import_count = 0
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            species_name = import_row['name']
            species_cares_status = import_row['cares_status']

            # validate Species data using Form validation
            species_form = SpeciesForm (import_row) # reads expected fields by header name
            if species_form.is_valid:
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
                    if species_cares_status != "NOTC":
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
        import_archive.name = current_user.get_display_name + "_species_import"
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
        report_row = ["Species Instance Name", "Import Status"]
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
                    if speciesInstance_form.is_valid:
                        species_instance = speciesInstance_form.save(commit=False)
                        species_instance.species = species
                        species_instance.user = current_user

                        # validate instance is unique - not a duplicate - cannot rely on simply name: must use name, species name, and user
                        if not SpeciesInstance.objects.filter(name=speciesInstance_name, user=current_user).exists():
                            report_row = [speciesInstance_name, "Validated: species instance is unique and new for this user, import successful"]
                            import_count = import_count + 1
                            speciesInstance_form.save() # commits to DB

                            # special case: re-importing previous species may have media images - try to restore them
                            instance_image = import_row['instance_image']
                            if instance_image != '':
                                if SpeciesInstance.objects.filter(name=speciesInstance_name).exists():
                                    newly_added_speciesInstance = SpeciesInstance.objects.get(name=speciesInstance_name, user=current_user)
                                    # seems like the following very simple 2 lines of code should happen via the species_form but it does not
                                    newly_added_speciesInstance.instance_image = instance_image
                                    newly_added_speciesInstance.save()
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
        import_archive.name = current_user.get_display_name + "_speciesInstance_import"
        import_archive.save()
    return


#Export Species List, SpeciesInstances, Aquarists


def export_csv_aquarists():
    aquaristSet = User.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aquarists_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(['username', 'email', 'first_name', 'last_name', 'state', 'country', 'date_joined', 
                     'is_private_name', 'is_private_email', 'is_private_location', 'is_staff', 'is_active'])
    for aqst in aquaristSet:
        writer.writerow([aqst.username, aqst.email, aqst.first_name, aqst.last_name, aqst.state, aqst.country, aqst.date_joined, 
                         aqst.is_private_name, aqst.is_private_email, aqst.is_private_location, aqst.is_staff, aqst.is_active])
    return response

def export_csv_species():
    speciesSet = Species.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="species_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(['name', 'category', 'global_region', 'local_distribution', 'species_image', 'cares_status', 'created', 'description'])
    for species in speciesSet:
        writer.writerow([species.name, species.category, species.global_region, species.local_distribution, species.species_image.name, species.cares_status, species.created, species.description])
    return response

def export_csv_speciesInstances():
    speciesInstances = SpeciesInstance.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="species_instance_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(['aquarist', 'name', 'species', 'unique_traits', 'instance_image', 'collection_point', 'genetic_traits', 'currently_keep', 
                    'approx_date_acquired', 'aquarist_notes', 'have_spawned', 'spawning_notes', 'have_reared_fry', 'fry_rearing_notes', 'young_available', 'created'])
    for speciesInstance in speciesInstances:
        writer.writerow([speciesInstance.user.username, speciesInstance.name, speciesInstance.species, speciesInstance.unique_traits, speciesInstance.instance_image.name, 
                         speciesInstance.collection_point, speciesInstance.genetic_traits, speciesInstance.currently_keep, speciesInstance.year_acquired,
                         speciesInstance.aquarist_notes, speciesInstance.have_spawned, speciesInstance.spawning_notes, speciesInstance.have_reared_fry, 
                         speciesInstance.fry_rearing_notes, speciesInstance.young_available, speciesInstance.created])
    return response
