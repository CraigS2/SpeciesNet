from species.models import Species, SpeciesInstance, ImportArchive
from species.forms import SpeciesForm, SpeciesInstanceForm
from django.db.models import FileField
from django.contrib.auth.models import User
from django.shortcuts import render
from django.views.generic.base import View
from django.http import HttpResponse
from django.core.files import File
from io import BytesIO
import csv
from csv import DictReader
from io import StringIO, TextIOWrapper
from django.core.files.base import ContentFile

# Import Species List, SpeciesInstances

def import_csv_species (import_archive: ImportArchive, current_user: User):
    print ("Current User: ", current_user)
    print ("Processing Species CSV file ", import_archive.import_csv_file.name)
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Species", "Import Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one species per row
        row_count = 0
        import_count = 0
        print ("Begin iterating rows")
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            species_name = import_row['name']
            print ("Species name is ", species_name)

            # validate Species data using Form validation
            species_form = SpeciesForm (import_row) # reads expected fields by header name
            print ('Row ', row_count, 'species validation: ', species_form.is_valid())
            if species_form.is_valid:
                species = species_form.save(commit=False)
                print ("Row ", row_count, " validates: ", import_row)
                
                # validate input species name and verify non-duplicate
                if not Species.objects.filter(name=species_name).exists():
                    print (species_name, "Validated: Species is unique and new, import successful")
                    report_row = [species_name, "Validated: Species is unique and new, import successful"]
                    import_count = import_count + 1
                    species_form.save()
                else:
                    print (species_name, "ERROR: species exists - cannot add duplicate species")
                    report_row = [species_name, "ERROR: species exists - cannot add duplicate species"]
            else:
                print (species_name, "ERROR: validation failure - cannot save species")
                report_row = [species_name, "ERROR: validation failure - cannot save species"]
            csv_report_writer.writerow(report_row)

        print ("Processed ", row_count, " csv records")

        # persist import report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.username + "_species_import_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)
        print ("Import results written to ", import_archive.import_results_file.name)

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

def import_csv_speciesInstances (import_archive: ImportArchive, current_user: User):
    print ("Current User: ", current_user)
    print ("Processing Species CSV file ", import_archive.import_csv_file.name)
    with open(import_archive.import_csv_file.path,'r', encoding="utf-8") as import_file:

        # create results csv file
        csv_report_buffer = StringIO()
        csv_report_writer = csv.writer(csv_report_buffer)
        report_row = ["Species Instance Name", "Import Status"]
        csv_report_writer.writerow(report_row)

        # batch process import one species per row
        row_count = 0
        import_count = 0
        print ("Begin iterating rows")
        for import_row in DictReader(import_file):
            row_count = row_count + 1
            speciesInstance_name = import_row['name']

            # validate Species exists - required to instantiate SpeciesInstance
            species_name = import_row['species']
            print ("Species name is ", species_name)
            if Species.objects.filter(name=species_name).exists():
                print (species_name, "Species exists - required for SpeciesInstance")
                species = Species.objects.get(name=species_name)
                print ('Fetched species: ', species.name)

                # validate pending SpeciesInstance object - will foreign key species resolve by name? TBD
                speciesInstance_form = SpeciesInstanceForm (import_row) # reads expected fields by header name
                print ('Row ', row_count, 'speciesInstance validation: ', speciesInstance_form.is_valid())
                if speciesInstance_form.is_valid:
                    species_instance = speciesInstance_form.save(commit=False)
                    print ("SpeciesInstance instantiated referencing species: ", species_instance.species)
                    species_instance.species = species
                    print ("SpeciesInstance instantiated referencing species: ", species_instance.species)
                    species_instance.user = current_user

                    # validate instance is unique - not a duplicate
                    if not SpeciesInstance.objects.filter(name=speciesInstance_name).exists():
                        print (speciesInstance_name, "Validated: species instance is unique and new, import successful")
                        report_row = [speciesInstance_name, "Validated: species instance is unique and new, import successful"]
                        import_count = import_count + 1
                        speciesInstance_form.save() # commits to DB
                    else:
                        print (species_name, "ERROR: species instance exists - cannot add duplicate")
                        report_row = [speciesInstance_name, "ERROR: species instance exists - cannot add duplicate"]
                else:
                    print (speciesInstance_name, "ERROR: validation failed - unable to create species instance")
                    report_row = [speciesInstance_name, "ERROR: validation failed - unable to create species instance"]
                        
            else:
                print (speciesInstance_name, "ERROR: species ", species_name, " does not exist - required for species instance")
                report_row = [speciesInstance_name, "ERROR: species ", species_name, " does not exist - required for species instance"]
            csv_report_writer.writerow(report_row)

        print ("Processed ", row_count, " csv records")

        # persist import report
        csv_report_file = ContentFile(csv_report_buffer.getvalue().encode('utf-8'))
        csv_report_filename = current_user.username + "_species_instance_import_log.csv"
        import_archive.import_results_file.save(csv_report_filename, csv_report_file)
        print ("Import results written to ", import_archive.import_results_file.name)

        # persist import archive
        import_archive.import_status = ImportArchive.ImportStatus.PARTIAL
        if import_count == 0:
            import_archive.import_status = ImportArchive.ImportStatus.FAIL
        else:
            if import_count == row_count:
                import_archive.import_status = ImportArchive.ImportStatus.FULL
        import_archive.name = current_user.username + "_speciesInstance_import"
        import_archive.save()
        print ("Import Archive saved: ", import_archive.name)
    return


#Export Species List, SpeciesInstances

def export_csv_species():
    speciesSet = Species.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="species_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(['name', 'category', 'global_region', 'local_distribution', 'species_image', 'description'])
    for species in speciesSet:
        writer.writerow([species.name, species.category, species.global_region, species.local_distribution, species.species_image.name, species.description])
    return response

def export_csv_speciesInstances():
    speciesInstances = SpeciesInstance.objects.all()
    response = HttpResponse (
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="species_instance_export.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(['aquarist', 'name', 'species', 'unique_traits', 'instance_image', 'collection_point', 'genetic_traits', 'num_adults', 'currently_keeping_species', 
                    'approx_date_acquired', 'aquarist_notes', 'have_spawned', 'spawning_notes', 'have_reared_fry', 'fry_rearing_notes', 'young_available'])
    for speciesInstance in speciesInstances:
        writer.writerow([speciesInstance.user.username, speciesInstance.name, speciesInstance.species, speciesInstance.unique_traits, speciesInstance.instance_image.name, 
                         speciesInstance.collection_point, speciesInstance.genetic_traits, speciesInstance.num_adults, speciesInstance.currently_keeping_species, 
                         speciesInstance.approx_date_acquired, speciesInstance.aquarist_notes, speciesInstance.have_spawned, speciesInstance.spawning_notes, 
                         speciesInstance.have_reared_fry, speciesInstance.fry_rearing_notes, speciesInstance.young_available])
    return response