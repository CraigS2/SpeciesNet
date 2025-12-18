# Build and run all tests
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Run tests and see output
docker-compose -f docker-compose.test.yml run --rm test_django

# Run specific test module
docker-compose -f docker-compose.test.yml run --rm test_django \
  python manage.py test species.tests. test_models -v 2

# Run specific test class
docker-compose -f docker-compose.test.yml run --rm test_django \
  python manage.py test species.tests.test_models. UserModelTest -v 2

# Run specific test method
docker-compose -f docker-compose.test.yml run --rm test_django \
  python manage.py test species.tests.test_models.UserModelTest.test_create_user -v 2

# Run with coverage
docker-compose -f docker-compose.test. yml run --rm test_django \
  sh -c "coverage run --source='species' manage.py test species.tests && coverage report"

# Keep test database between runs (faster iteration)
docker-compose -f docker-compose.test.yml run --rm test_django \
  python manage.py test species.tests --keepdb

# Clean up test containers and volumes
docker-compose -f docker-compose.test.yml down -v

###########################################################
# Chat notes 

# Build and start up
docker-compose -f docker-compose.test.yml up --build

# Remove the old containers and images
docker-compose -f docker-compose.test.yml down -v  # -v option removes volumes!
docker system prune -f

# Rebuild from scratch
docker-compose -f docker-compose.test.yml build --no-cache
docker-compose -f docker-compose.test.yml up

###########################################################
# First run (builds image)
docker-compose -f docker-compose.test.yml up --build

# Stop and re-run after editing test files (no rebuild needed!)
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose. test.yml up

#############################################################
# running the container without executing entrypoint.sh - then enter cmds
docker-compose -f docker-compose.test.yml run --rm test_django bash
python manage.py migrate
python manage.py test species.tests -v 2
python manage.py test species.tests.test_views_species -v 2

#############################################################
# To run automated tests - must clean out containers each time because of Volume mgmt issues - TODO Fix
docker-compose -f docker-compose.test.yml down -v 
docker-compose -f docker-compose.test.yml up --build

#############################################################
# Build caching issues!?! To force a clean build - takes along time - rebuilds from scratch ouch!
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml build --no-cache test_django
docker-compose -f docker-compose.test.yml up --build

# -- or --

docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml build --no-cache test_django
docker-compose -f docker-compose.test.yml up -d test_db
docker-compose -f docker-compose.test.yml run --rm test_django python manage.py test species.tests.test_views_species_instance -v 2

#############################################################
# -v verbose options
# -v 0 (or no -v): Minimal output - just dots and summary
# -v 1: Shows test class names
# -v 2: Shows test names AND docstrings

#############################################################
# To run just one set of tests in a single python file - start up the db only, then execute the test
docker-compose -f docker-compose.test.yml up -d test_db
sleep 5 (wait a bit for DB to be ready)
docker-compose -f docker-compose.test.yml run --rm test_django python manage.py test species.tests.test_views_species_instance -v 2


docker-compose -f docker-compose.test.yml run --rm test_django python manage.py test species.tests.test_views_species_instance -v 2

#############################################################
# To build and then run just one set of tests in a single python file - or run just a single test

docker-compose -f docker-compose.test.yml build
docker-compose -f docker-compose.test.yml run --rm test_django python manage.py test species.tests.test_views_species_instance -v 2

#############################################################
# To run just one set of tests in test class within a single python file
docker-compose -f docker-compose. test.yml run --rm test_django python manage.py test species. tests.test_views_species_instance.SpeciesInstanceCreateViewTest -v 2

#############################################################
# To run just one test in a test class within a single python file ... whew that's a long command line string!
docker-compose -f docker-compose. test.yml run --rm test_django python manage.py test species. tests.test_views_species_instance.SpeciesInstanceCreateViewTest.test_create_species_instance_with_valid_data -v 2

