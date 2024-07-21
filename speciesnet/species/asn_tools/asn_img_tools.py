from PIL import Image
from pillow_heif import register_heif_opener
#from django.db import models
from django.db.models import ImageField
from django.core.files import File
from io import BytesIO
import os
from django.conf import settings
from django.contrib import messages


def processUploadedImageFile (image_field: ImageField, species_or_instance_name, request):
    #register_heif_opener() # must be done before form upload or rejects heic files
    print ("Process Image: ", image_field.path)
    img = Image.open(image_field.path)

    split_path = os.path.split(image_field.path)
    uploaded_image_filename = split_path[1]

    split_path = os.path.splitext(image_field.path)
    curExt = split_path[1]
    curExt = curExt.lower()
    jpgExt = ".jpg"
    print ("Current file extension:   ", curExt) 

    # save image file with name based on species or instance name
    new_image_name = species_or_instance_name + jpgExt
    new_image_name = new_image_name.lower()
    new_image_name = new_image_name.replace(" ", "_")
    print ("Revised image file name:  ", new_image_name)

    try:

        # fix for png image support - png images support transparency
        if img.mode == 'RGBA':
            print ("Merge transparency to allow image conversion from RGBA to RGB")
            fill_color = '#E5E4E2'  # platinum very light grey default background color
            background = Image.new(img.mode[:-1], img.size, fill_color)
            background.paste(img, img.split()[-1])
            img = background

        if not img.mode == 'RGB':
            print ("Converting ", image_field.name, " to RGB mode")
            img.convert('RGB')    # fails without .png fix above throws OSError: cannot write mode RGBA as JPEG

        # resize to 320x240
        print ("Uploaded image resolution: ", image_field.width, "x", image_field.height)
        print ("Resize image to 320 x 240")
        img.thumbnail((320, 240))

        # save the new .jpg and delete the original uploaded file
        print ("Resize complete. Save as new .jpg file and delete the original uploaded file")
        memBlob = BytesIO()
        memBlob.seek(0)
        img.save(memBlob, 'JPEG', quality=95)
        print ("File saved as jpg quality=95")

        # update Django image_field to newly saved file - deletes the old image
        print ("Deleting previous image_field image file")
        print ("ImageField save with new filename: ", new_image_name)
        image_field.delete (save=False) # deletes old file and sets image_field empty
        image_field.save(new_image_name, File(memBlob))

        print ("Closing img")
        img.close()

        print ("Done image processing without exceptions")

    except OSError:

        error_msg = ("Error processing uploaded image file: " + uploaded_image_filename)
        print (error_msg)
        messages.error (request, error_msg)
        try:
            img.close()
        except OSError:
            print ("Unable to close opened image file")

    return