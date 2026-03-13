#!/bin/sh

python << END
import sys
import time
import MySQLdb
suggest_unrecoverable_after = 30
start = time.time()

while True:
    try:
        _db = MySQLdb._mysql.connect(
            host="${DATABASE_HOST:-db}",
            user="${DATABASE_USER-mysqluser}",
            password="${DATABASE_PASSWORD-unsecure}",
            database="${DATABASE_NAME-speciesnet}",
            port=int("${DATABASE_PORT-3306}")
        )
        break
    except MySQLdb._exceptions.OperationalError:
        sys.stderr.write("Waiting for MySQL to become available...\n")
        if time.time() - start > suggest_unrecoverable_after:
            sys.stderr.write("  This is taking longer than expected. The following exception may be indicative of an unrecoverable error: '{}'\n".format(error))
    time.sleep(1)
END

### only use migrations when you know they are needed ###
python manage.py init_sites
#python manage.py showmigrations
#python manage.py makemigrations --no-input
python manage.py migrate --no-input
python manage.py collectstatic --no-input
#python manage.py collectstatic --noinput --clear

if [ ! -z "$SUPER_USER_NAME" ] && [ ! -z "$SUPER_USER_EMAIL" ] && [ ! -z "$SUPER_USER_PASSWORD" ]; then
    DJANGO_SUPERUSER_PASSWORD=$SUPER_USER_PASSWORD python manage.py createsuperuser --username $SUPER_USER_NAME --email $SUPER_USER_EMAIL --noinput 2>/dev/null \
        || echo "Superuser already exists or creation skipped"
fi

# Create API service user if environment credentials are set
if [ ! -z "$API_SERVICE_EMAIL" ] && [ ! -z "$API_SERVICE_PASSWORD" ]; then
    echo "Creating/updating API service user..."
    python manage.py create_api_user
fi

if [ "${DEBUG}" != "1" ]; then
    echo Starting in production mode
    gunicorn speciesnet.wsgi:application --bind 0.0.0.0:8000
else
    echo Running in development mode
    gunicorn speciesnet.wsgi:application --bind 0.0.0.0:8000 --reload
    # extended timeout needed for dev-only beta CollectSpeciesData aggregation
    #gunicorn speciesnet.wsgi:application --bind 0.0.0.0:8000 --reload --timeout 1200
fi