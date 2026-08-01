"""Bring the database schema up to date, creating it on the first start.

The migration chain cannot be replayed against an empty database: early
revisions drop foreign keys by the names MySQL generates automatically
(``regression_test_ibfk_1`` and friends), and those exist only when the
schema was first built from the models rather than from the migrations. A
fresh database is therefore created from the models and stamped at the
current head, which is what the application does anyway on its first
request. A database that already carries an ``alembic_version`` table -- an
existing environment, or one restored from a dump -- only gets the pending
migrations applied.

Creating the tables is deliberately skipped in that second case: doing both
would let ``create_all`` add a table that a pending migration still expects
to create itself, which then fails.

A fresh database is also seeded, because several pages read rows they assume
are always present -- the home page dereferences the ``last_commit`` entry
without a null check -- and an empty schema alone therefore serves a 500.
"""
import subprocess
import sys
from os import path

from flask_migrate import stamp, upgrade
from sqlalchemy import create_engine, inspect

# Need to append server root path to ensure we can import the necessary files.
ROOT = path.dirname(path.dirname(path.abspath(__file__)))
sys.path.append(ROOT)


def main() -> int:
    """Create or migrate the schema, depending on what is already there."""
    from database import create_session
    from run import app, config

    uri = config['DATABASE_URI']
    engine = create_engine(uri)
    try:
        established = inspect(engine).has_table('alembic_version')
    finally:
        engine.dispose()

    with app.app_context():
        if established:
            print('existing database: applying pending migrations', flush=True)
            upgrade()
        else:
            print('fresh database: creating schema from the models', flush=True)
            create_session(uri)
            stamp()

    if not established:
        # Run out of process: sample_db seeds on import and reads the URI from
        # argv, so it cannot simply be called.
        print('seeding development data', flush=True)
        subprocess.check_call(
            [sys.executable, path.join(ROOT, 'install', 'sample_db.py'), uri])

    print('schema is up to date', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
