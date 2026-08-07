#!/bin/sh
# Shared DB-wait helper for services that bypass entrypoint.sh (celery worker/beat).
# Waits for MySQL/MariaDB to accept connections, then waits for Django migrations
# if they need to run to be fully applied before allowing the caller to proceed.

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
        _db.close()
        sys.stdout.write("MySQL is available, continuing...\n")
        break
    except MySQLdb._exceptions.OperationalError as error:
        sys.stderr.write("Waiting for MySQL to become available...\n")
        if time.time() - start > suggest_unrecoverable_after:
            sys.stderr.write("  This is taking longer than expected. The following exception may be indicative of an unrecoverable error: '{}'\n".format(error))
    time.sleep(1)
END

echo "Waiting for Django migrations to be fully applied..."
migration_wait_start=$(date +%s)
migration_suggest_unrecoverable_after=120

until python manage.py migrate --check > /dev/null 2>&1; do
    now=$(date +%s)
    elapsed=$((now - migration_wait_start))
    echo "  Migrations not yet fully applied, waiting... (${elapsed}s elapsed)"
    if [ "$elapsed" -gt "$migration_suggest_unrecoverable_after" ]; then
        echo "  This is taking longer than expected (>${migration_suggest_unrecoverable_after}s)."
        echo "  If django_gunicorn is not running or its migrate step failed, this will wait forever."
    fi
    sleep 2
done

echo "Migrations confirmed applied, continuing..."