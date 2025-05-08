from io import BytesIO
from PIL import Image
#from django.shortcuts import render, redirect
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
#from .forms import LabelFormSet
#from .models import LabelEntry
from species.forms import SpeciesInstanceLabelFormSet


def generatePdfFile (formset: SpeciesInstanceLabelFormSet, label_set):
    
    # Configure PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="AquaristSpecies_Labels.pdf"'

    if formset.is_valid():
        # Pull form text input by user and persist labels for pfd gen and future defaults
        label_counter = 0
        for form in formset:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                # assume order is maintained TODO find a better way to do this
                si_label = label_set[label_counter]
                si_label.name = form.cleaned_data['name']
                si_label.text = form.cleaned_data['text']
                si_label.save() 
                label_counter += 1

        # reportlab pdf creation

        buffer = BytesIO()
        c = canvas.Canvas(response, pagesize=letter)
        c.setTitle ("Aquarist Species Labels")
        
        # Avery 5162 specifications 
        # 14 labels 1.33"x4" per 8.5"x11" sheet 2 columns of 7 labels

        label_width = 4.0 * inch
        label_height = 1.35 * inch  # 1.33 spec
        margin_left = 0.03 * inch   # Left margin 0.17 spec
        margin_top  = 0.88 * inch   # Top margin 0.83 spec
            
        # QR code specifications
        qr_size = 0.8 * inch  # square QR code
        
        # Generate labels
        current_label = 0
        total_labels = len(label_set)
        
        while current_label < total_labels:

            if current_label > 0 and current_label % 14 == 0:
                c.showPage()  # Start a new page after every 14 labels
            
            # Calculate label position uses % modulus operator which returns remainder after division

            row = (current_label % 14) // 2   
            col = (current_label % 14) % 2     
            
            # positioning on canvas is done using 'points' unit where 1 point = 1/72 of an inch

            x = margin_left + (col * label_width) + (col * 10) # adjust 2nd column offset ~ 0.14" to right
            y = letter[1] - margin_top - (row * label_height)

            si_label = label_set[current_label]

            c.drawImage(si_label.qr_code.path, x + 0.20*inch, y - 1.0*inch, width=1.0*inch, height=1.0*inch)
            c.setFont("Helvetica-Bold", 10)  
            c.drawString(x + qr_size + 0.45*inch, y - 0.4*inch, si_label.name)
            c.setFont("Helvetica", 8)  
            c.drawString(x + qr_size + 0.45*inch, y - 0.6*inch, si_label.text)
            
            current_label += 1
        
        c.showPage() 
        c.save()
        
        pdf = buffer.getvalue()
        buffer.close()

        response.write(pdf)

        return response
