#!/usr/local/bin/python3
"""Root module to manage flask script commands."""
import os
import unittest

from flask_script import Command, Manager

from mod_regression.controllers import mod_regression
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
        """Driver function for update subcommand."""
        if len(remaining) == 0:
            print('path to ccextractor is missing')
            return 1
        else:
            path_to_ccex = remaining[0]
            print('path to ccextractor: ' + str(path_to_ccex))

            if update_expected_results(path_to_ccex):
                print('update function finished')
            else:
                print('update function errored')
                return 1

        return 0


if __name__ == '__main__':
    manager.run()
