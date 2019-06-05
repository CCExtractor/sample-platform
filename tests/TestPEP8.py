"""Provides sanity testing for PEP8 issues."""

import os

import pycodestyle

from .base import BaseTestCase

PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPEP8(BaseTestCase):
    """Test the root folder for PEP8 issues."""

    def test_conformance(self):
        """Test that the code conforms to PEP-8."""
        style = pycodestyle.StyleGuide(config_file=os.path.join(PROJ_DIR, '.pycodestylerc'))
        result = style.check_files(self.get_all_py_files())
        self.assertEqual(result.total_errors, 0,
                         "Found code style errors (and warnings).")

    @staticmethod
    def get_all_py_files():
        """
        Get all python files present in the project directory.

        :return: list of python files in the project
        :rtype: list
        """
        py_file_list = []
        for root, _, files in os.walk(PROJ_DIR):
            for file in files:
                if '.py' == file[-3:]:
                    py_file_list.append(os.path.join(root, file))
        return py_file_list
