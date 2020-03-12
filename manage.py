#!/usr/local/bin/python3
"""Root module to manage flask script commands."""
from exceptions import CCExtractorEndedWithNonZero, MissingPathToCCExtractor

from flask_script import Command, Manager

from mod_regression.update_regression import update_expected_results
from run import app

manager = Manager(app)


@manager.add_command
class UpdateResults(Command):
    """
    Update results for the present samples with new ccextractor version.

    Pass path to CCExtractor binary as the first argument. Example, `python manage.py update /path/to/ccextractor`
    """

    name = 'update'
    capture_all_args = True

    def run(self, remaining):
        """Driver function for update command."""
        if len(remaining) == 0:
            print('path to ccextractor is missing')
            raise MissingPathToCCExtractor

        path_to_ccex = remaining[0]
        print(f'path to ccextractor: {path_to_ccex}')

        if not update_expected_results(path_to_ccex):
            print('update function errored')
            raise CCExtractorEndedWithNonZero

        print('update function finished')
        return 0


if __name__ == '__main__':
    manager.run()
