import os
import sys
import shutil
import subprocess
import shlex
from .base import BaseTestCase, load_config
from mock import mock, patch

class TestMigrate(BaseTestCase):
    def setUp(self):
        try:
            shutil.rmtree('migrations')
        except OSError:
            pass

    def tearDown(self):
        try:
            shutil.rmtree('migrations')
        except OSError:
            pass

    @mock.patch('sys.exit')
    @mock.patch('config_parser.parse_config', side_effect=load_config)
    def test_migrate_upgrade(self, mock_config, mock_exit):
        from db_migrate import manager
        testargs = ["python3 db_manage.py", "db", "init"]
        with patch.object(sys, 'argv', testargs):
            manager.run()
            mock_exit.assert_called_with(0)
        testargs = ["python3 db_manage.py", "db", "migrate"]
        with patch.object(sys, 'argv', testargs):
            manager.run()
            mock_exit.assert_called_with(0)
        from database import Base
        # testargs = ["python3 db_manage.py", "db", "upgrade"]
        # with patch.object(sys, 'argv', testargs):
        #     manager.run()
        #     mock_exit.assert_called_with(0)
