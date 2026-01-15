from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
#from django.db import models
from django.db.models import ImageField
from django.core.files import File
from io import BytesIO
import os
import qrcode
from django.conf import settings
from django.contrib import messages


def processUploadedImageFile (image_field: ImageField, species_or_instance_name, request):
    #register_heif_opener() # must be done before form upload or rejects heic files
    img = Image.open(image_field.path)

    split_path = os.path.split(image_field.path)
    uploaded_image_filename = split_path[1]

    split_path = os.path.splitext(image_field.path)
    curExt = split_path[1]
    curExt = curExt.lower()
    jpgExt = ".jpg"

    # save image file with name based on species or instance name
    new_image_name = species_or_instance_name + jpgExt
    new_image_name = new_image_name.lower()
    new_image_name = new_image_name.replace(" ", "_")

    # fix for cameras/phones which require EXIF orientation tag and image rotation. Orientation values:
    # 1: Normal (0°), 2: Flipped horizontally (mirrored), 3: Rotated 180°, 4: Flipped vertically,
    # 5: Rotated 90° CCW, then flipped horizontally, 6: Rotated 90° CW (Clockwise) - common for portrait photos,
    # 7: Rotated 90° CW, then flipped horizontally, 8: Rotated 90° CCW (Counter-clockwise)
    transpose_img = False
    try: 
        exif = img.getexif()
        if exif:
            orientation = exif.get(0x0112) # orientation tag
            if orientation is not None: 
                try:
                    orientation = int(orientation)
                    if orientation > 1:
                        transpose_img = True
                        print('Image transpose needed - EXIF orientation: ' + str(orientation))
                except (ValueError, TypeError):
                    print('Image processing exception: invalid EXIF orientation: ' + str(orientation))
    except Exception as e:
        print('Image processing exception: Could not read EXIF data: ' + str(e))
    
    try:
        # fix for cameras/phones which require EXIF orientation read and matching transpose
        if transpose_img:
            img = ImageOps.exif_transpose(img)
            print('Image transposed to manageEXIF orientation')
            
        # fix for png image support - png images support transparency
        if img.mode == 'RGBA':
            fill_color = '#E5E4E2'  # platinum very light grey default background color
            background = Image.new(img.mode[:-1], img.size, fill_color)
            background.paste(img, img.split()[-1])
            img = background

        if not img.mode == 'RGB':
            img.convert('RGB')    # fails without .png fix above throws OSError: cannot write mode RGBA as JPEG

        # resize to 480x320
        img.thumbnail((480, 320))

        # save the new .jpg and delete the original uploaded file
        memBlob = BytesIO()
        memBlob.seek(0)
        img.save(memBlob, 'JPEG', quality=95)

        # update Django image_field to newly saved file - deletes the old image
        image_field.delete (save=False) # deletes old file and sets image_field empty
        image_field.save(new_image_name, File(memBlob))

        img.close()

    except OSError:
        error_msg = ("Error processing uploaded image file: " + uploaded_image_filename)
        messages.error (request, error_msg)
        try:
            img.close()
        except OSError:
            print ("Unable to close opened image file")
    return


def generate_qr_code (image_field: ImageField, url_text, species_or_instance_name, request):

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )

    qr.add_data(url_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    name = species_or_instance_name + '_qr_code'
    image_field.save(name, File(buffer))
    img.close()

    return