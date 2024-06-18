# SpeciesNet

SpeciesNet is a Django project which builds an Aquarist's Species networking site. 
The site has 3 primary model objects: Users (Aquarists), Species, and SpeciesInstances

Users: Django Custom User Model
Species: An extensible list of unique Species defined using traditional 'Genus species' nomenclature
SpeciesInstances: An extensible list of Species kept by Users (Aquarists)

The primary use cases for the site include 'publishing Species & Species Instances' and 
'finding Species of interest'. The site relies on a crowd-sourced approach allowing any user to
add a new species (must be unique) and create a species instance ('I keep this species')

-----------------------------------
SpeciesNet setup notes:

Prequisits: git, python3, pip3, nginx, and docker-compose
    >> sudo apt install python3 python3-pip git, nginx, docker-compose

NGINX defaults to auto-start which can interfere with the docker-compose spin-up of NGINX
Disable autostart:
      >> sudo update-rc.d -f nginx disable

Choose your development folder and clone the repository:
    >> git clone https://github.com/CraigS2/SpeciesNet.git

Create and activate a virtual environement using python
    >> python3 -m venv ./asn_venv
	  >> source ./asn_venv/bin/activate

Note you can exit the virtual environment anytime with the cmd 'deactivate'
	
Requirements.txt declares all Django project package dependencies. 
These will be installed at build time using docker-compose

Django==3.0.8
gunicorn==20.0.4
pillow==9.5.0
pillow_heif==0.12
mysqlclient==2.1.1
sqlparse==0.4.4
	
DB support includes the default db.sqlite3 and mySQL
To enable mySQL uncomment the settings.py code and comment out db.sqlite3
	
The .env.example file is a blank template. A .env file must be populated in the same folder location.

Use docker-compose to run the project using a non-root superuser
      >> sudo docker-compose up --build
CTRL-C gracefully exits the Django gunicorn and NGINX services