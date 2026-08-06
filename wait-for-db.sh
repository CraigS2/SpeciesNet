#!/bin/sh
# Shared DB-wait helper for services that bypass entrypoint.sh (celery worker/beat).
# Waits for MySQL/MariaDB to accept connections before continuing.

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