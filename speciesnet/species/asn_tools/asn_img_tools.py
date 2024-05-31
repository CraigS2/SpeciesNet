from PIL import Image
from pillow_heif import register_heif_opener
#from django.db import models
from django.db.models import ImageField
from django.core.files import File
from io import BytesIO
import os
from django.conf import settings


def processUploadedImageFile (image_field: ImageField, species_or_instance_name ):
    #register_heif_opener() # must be done before form upload or rejects heic files
    print ("Process Image: ", image_field.path)
    
    img = Image.open(image_field.path)
    print ("Image resolution: ", image_field.width, "x", image_field.height)
    if not img.mode == 'RGB':
        print ("Converting ", image_field.name, " image to RGB format")
        img = img.convert('RGB')

    print ("Resize image to 320 x 240")
    img.thumbnail((320, 240))
    
    # manage filename as species name and file format to .jpg

    cur_image_file_noext, curExt = os.path.splitext(image_field.path)
    curExt = curExt.lower()
    jpgExt = ".jpg"
    
    #print ("Current image file noext: ", cur_image_file_noext) 
    print ("Current file extension:   ", curExt) 

    #if curExt != ".jpg":
    #print ("Converting ", image_field.name, " image file to .jpg")
    #cur_image_name_noext, curExt = os.path.splitext(image_field.name)
    #cur_image_name = cur_image_name_noext + jpgExt
    new_image_name = species_or_instance_name + jpgExt
    new_image_name = new_image_name.lower()
    new_image_name = new_image_name.replace(" ", "_")
    print ("Revised image file name:  ", new_image_name)

    memBlob = BytesIO()
    img.save(memBlob, 'JPEG', quality=85)
    memBlob.seek(0)

    image_field.delete (save=False) # deletes old file and sets image_field empty
    print ("ImageField deleted wo file save.")

    #base_filename = os.path.basename(cur_image_name)
    #print ("ImageField save with base filename: ", base_filename)
    print ("ImageField save with new filename: ", new_image_name)
    image_field.save(new_image_name, File(memBlob))
    img.close()

    return