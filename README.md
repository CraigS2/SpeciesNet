# SpeciesNet

SpeciesNet is a Django project which builds an Aquarist's Species networking site. 
The site has 3 primary model objects: Users (Aquarists), Species (single Declarations), and SpeciesInstances (Aquarist Species)

Users: Django Custom User Model. All users are assumed to be Aquarists who keep fish.

Species: A table of unique Species defined using traditional 'Genus species' nomenclature. Each unique species
is a single entry shared by all Aquarists keeping this species. An optional CARES attribute can be used to emphasize CARES Species. 

SpeciesInstances: Labeled as 'Aquarist Species' in the UI, it defines a table of species kept by Users. Each instance is dependent on a single Species declaration. 

The primary use cases for the site include Searching Species, browsing other User Aquarist Species, adding and editing your own Aquarist Species, and emailing Users who are keeping fish of interest. Users can also declare a Species in the database, if it does not already exist. 

Additional features include an optional Aquarist Species Log where users can add additional photos and notes on the species they keep, and a shared Species Maintenance Group where Users can collaborate on the breeding and maitenance of a Species. 

-----------------------------------

SpeciesNet setup notes:

Prequisits: git, python3, docker-compose

Because Docker Containers are used for nginx, django, and the mariadb database, no virtual environement 
is needed. Use a terminal and clone the repo from a working folder. Navigate to the SpeciesNet folder and copy the sample.env file:

    cp sample.env .env

Defaults provided in the sample.env file enable immediate startup without editing environment variables.

To build and run the project execute the following command from the SpeciesNet folder:

    docker compose up --build

CTRL-C gracefully stops the 3 running docker containers. A default developer-friendly nginx configuration default.conf is used. 

Running Docker Containers include Django Gunicorn, MariaDB, and Nginx with Certbot integration. 
	
Requirements.txt declares all Django project package dependencies. These will be installed at build time using docker-compose. 

This project has been developed, tested, and deployed on Ubuntu development machines and servers.

