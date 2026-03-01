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

SpeciesNet developer Setup

Prequisits: Ubuntu OS with docker

To get the latest source from github and build/run locally:

1. Create a working 'dev' folder in your home directory on a linux machine or virtual machine with docker installed. 

2. The GitHub open source project is located at: https://github.com/CraigS2/SpeciesNet 
   The GitHub git repository is located at: https://github.com/CraigS2/SpeciesNet.git
    Navigate to your empty 'dev' directory and clone the repo with the following command:
	
	    git clone https://github.com/CraigS2/SpeciesNet.git
		
	This will create a copy of the git repot and populate the 'SpeciesNet' subfolder with the current set of files matching the master branch and synched to 'head' (most recent changes)
	
3. All development work generallly happens from a command line within this new folder

        cd SpeciesNet
		
	If you want to work on an existing branch - typical for new feature development - you can optionally switch to this branch:
	
	    git switch <branch_name>
		
    Where <branch_name> is the ah, well, branch name. For example cares01, cares02, etc.
    Always begin development by modifying files from the actual branch you want to work in, if it exists, or you can create a new branch for your own work (a good best practice)
	
4. To build and run you need the .env file configured. To get started, simply copy the sample.env file

        cp sample.env .env
		
5. Build and start the 3 docker containers: nginx (web server), gunicorn (django service),  and mariadb (database) with a clean build using the following docker compose command:

        docker compose up --build	
		
	The first time you build will take a while as all the dependent packages declared in requirements.txt are pulled down and the first full build is completed. Just let it run.
	Once the build is done, assuming you have no errors, you should see:
	
	    ✔ Container ASN_DB   Created 
        ✔ Container ASN_DJANGO  Created 
        ✔ Container NGINX_CBOT  Created 
        Attaching to ASN_DB, ASN_DJANGO, NGINX_CBOT
		
	Followed by command line output providing info that can be helpful in monitoring the startup and troubleshooting in cases of errors.
	
        ASN_DJANGO  | WARNINGS:
        ASN_DJANGO  | account.EmailAddress: (models.W036) MariaDB does not support unique constraints with conditions.
        ASN_DJANGO  | 	HINT: A constraint won't be created. Silence this warning if you don't care about it.
        ASN_DJANGO  | account.EmailAddress: (models.W036) MariaDB does not support unique constraints with conditions.
        ASN_DJANGO  | 	HINT: A constraint won't be created. Silence this warning if you don't care about it.
        ASN_DJANGO  | Operations to perform:
        ASN_DJANGO  |   Apply all migrations: account, admin, auth, contenttypes, sessions, sites, socialaccount, species
        ASN_DJANGO  | Running migrations:
        ASN_DJANGO  |   No migrations to apply.
        ASN_DJANGO  | DEBUG = True
        ASN_DJANGO  | DEBUG_TOOLBAR is enabled!
        ASN_DJANGO  | 
        ASN_DJANGO  | 0 static files copied to '/static', 163 unmodified.
        ASN_DJANGO  | Running in development mode
        ASN_DJANGO  | [2026-02-25 14:45:08 +0000] [10] [INFO] Starting gunicorn 23.0.0
        ASN_DJANGO  | [2026-02-25 14:45:08 +0000] [10] [INFO] Listening at: http://0.0.0.0:8000 (10)
        ASN_DJANGO  | [2026-02-25 14:45:08 +0000] [10] [INFO] Using worker: sync
        ASN_DJANGO  | [2026-02-25 14:45:08 +0000] [11] [INFO] Booting worker with pid: 11	

    Once you see this output you can launch your local browser (Firefox is good, standard on Ubuntu, or Chrome) and enter the address:
	
	    http://localhost/
		
	This will bring up the site and default to the home page. 
	
	If you experience errors during startup, which happens from time to time, troubleshooting is needed. Usuallly the command line output provide solid hints or better. 
	These days you can just describe your startup problem with a django project running in docker containers, include the helpful output, and AI feedback will help you troubleshoot. 
	
6. Stopping, bringing the containers back 'up', and removing the containers is done with the following docker commands:

        docker compose stop                       (stops but does not remove the containers)
		docker compose up -d                      (starts the containers running in the background - no command output seen so you have to wait for the startup)
		docker compose down                     (removes the containers)
		
7. Source files can be modified using any compatible IDE. Visual Studio Community edition is very good and is available free. Install it, and open the SpeciesNet folder. 

8. Git is the current standard for repository management and is both free open-source and excellent. However it lacks a GUI and is rather command-line intensive. 
    GitKraken is an excellent Git Mgmt tool with a friendly GUI and tools for common tasks like commits (source file changes) and synching with GitHub. 
	GitKraken is free for non-commercial use and requires any GitHub repos be open source to enable the free license. Download and install, and open the SpeciesNet folder. 

-----------------------------------
