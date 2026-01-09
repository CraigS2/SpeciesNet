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
            host="${DATABASE_HOST:-test_db}",
            user="${DATABASE_USER:-test_user}",
            password="${DATABASE_PASSWORD:-test_password}",
            database="${DATABASE_NAME:-test_speciesnet}",
            port=int("${DATABASE_PORT:-3306}")
        )
        _db.close()
        sys.stdout.write("MySQL test database is ready!\n")
        break
    except MySQLdb._exceptions. OperationalError as error:
        sys.stderr.write("Waiting for MySQL to become available...\n")
        if time.time() - start > suggest_unrecoverable_after: 
            sys.stderr.write(f"  This is taking longer than expected:  {error}\n")
    time.sleep(1)
END

#echo "Running migrations..." Not Needed as Test DB gets created and initialized separately
#python manage.py migrate --no-input

echo "Running tests..."
python manage.py test species.tests -v 2