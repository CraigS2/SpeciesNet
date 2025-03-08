# SpeciesNet

SpeciesNet is a Django project which builds an Aquarist's Species networking site. 
The site has 3 primary model objects: Users (Aquarists), Species (single Declarations), and SpeciesInstances (Aquarist Species)

Users: Django Custom User Model. All users are assumed to be Aquarists who keep fish.

Species: A table of unique Species defined using traditional 'Genus species' nomenclature. Each unique species
is a single entry shared by all Aquarists keeping this species. 

SpeciesInstances: A table of Aquarist Species kept by Users. Each instance is dependent on a Species declaration. 

The primary use cases for the site include 'Declaring Species' in the database, browsing to find Aquarists keeping a species,
and adding new Aquarist Species entries. You can also contact aquarists anonymously using email.

The site relies on a crowd-sourced approach allowing any user to
add a new species (must be unique) and add their species instance (the 'Aquarist Species' they keep)

-----------------------------------

SpeciesNet setup notes:

Prequisits: git, python3, docker-compose

Because Docker Containers are used for nginx, django, and the mariadb database, no virtual environement 
is needed. Use a terminal and navigate to the SpeciesNet folder, use the sample.env to create your own .env environment 
variable file, and run 'docker compose up --build'. CTRL-C gracefully stops the Django gunicorn, MariaDB, and NGINX services
	
Requirements.txt declares all Django project package dependencies. These will be installed at build time using docker-compose. 

Only tested and run on Ubuntu development machines and servers.

