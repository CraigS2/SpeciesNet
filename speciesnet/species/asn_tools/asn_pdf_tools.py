from io import BytesIO
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from species.forms import SpeciesInstanceLabelFormSet
from django.contrib import messages


def generatePdfLabels (formset: SpeciesInstanceLabelFormSet, label_set, request, response: HttpResponse):
    
    if formset.is_valid():
        # Pull form text input by user and persist labels for pfd gen and future defaults
        try:
            label_counter = 0
            label_num = []
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    si_label = label_set[label_counter]
                    si_label.name = form.cleaned_data['name']
                    si_label.text_line1 = form.cleaned_data['text_line1']
                    si_label.text_line2 = form.cleaned_data['text_line2']
                    si_label.save() 
                    label_num.append(form.cleaned_data['number'])
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
            species_label_count = len(label_set)
            current_species_label = 0
            
            while current_species_label < species_label_count:

                si_label = label_set[current_species_label]
                url_text = 'https://AquaristSpecies.net/speciesInstance/' + str(si_label.speciesInstance.id) + '/'
                label_count = label_num[current_species_label]

                while label_count >= 1:

                    if current_label > 0 and current_label % 14 == 0:
                        c.showPage()  # Start a new page after every 14 labels
                    
                    # Calculate label position uses % modulus operator which returns remainder after division

                    row = (current_label % 14) // 2   
                    col = (current_label % 14) % 2     
                    
                    # positioning on canvas is done using 'points' unit where 1 point = 1/72 of an inch

                    x = margin_left + (col * label_width) + (col * 10) # adjust 2nd column offset ~ 0.14" to right
                    y = letter[1] - margin_top - (row * label_height)

                    c.drawImage(si_label.qr_code.path, x + 0.20*inch, y - 1.0*inch, width=1.0*inch, height=1.0*inch)
                    c.setFont("Helvetica-Bold", 10)  
                    if si_label.name != '':
                        c.drawString(x + qr_size + 0.45*inch, y - 0.20*inch, si_label.name)
                    c.setFont("Helvetica", 8) 
                    if si_label.text_line1 != '':
                        c.drawString(x + qr_size + 0.45*inch, y - 0.47*inch, si_label.text_line1)
                    if si_label.text_line2 != '':
                        c.drawString(x + qr_size + 0.45*inch, y - 0.67*inch, si_label.text_line2)
                    #c.setFont("Times-Roman", 8)
                    c.setFont("Helvetica-Oblique", 8)
                    c.drawString(x + qr_size + 0.45*inch, y - 0.92*inch, url_text)            
                
                    label_count = label_count - 1
                    current_label += 1

                current_species_label += 1
            
            c.showPage() 
            c.save()
            
            pdf = buffer.getvalue()
            buffer.close()

            response.write(pdf)

        except Exception as e:
            error_msg = ("Error processing PDF file: " + str(e))
            messages.error (request, error_msg)

    return response
