"""Unit tests for Celery tasks and related controller functions."""

import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

from flask import g

from mod_test.models import TestType
from tests.base import BaseTestCase


class TestTriggerTestTasks(BaseTestCase):
    """Test cases for trigger_test_tasks function."""

    def test_trigger_test_tasks_disabled_by_default(self):
        """Test that tasks are not triggered when USE_CELERY_TASKS is False (default)."""
        from mod_ci.controllers import trigger_test_tasks

        # By default, USE_CELERY_TASKS is False
        with self.app.app_context():
            # Should not raise exception and should log debug message
            trigger_test_tasks([1, 2], 'fake_token')
            # Function returns silently when disabled

    def test_trigger_test_tasks_empty_list(self):
        """Test that empty list doesn't trigger any tasks."""
        from mod_ci.controllers import trigger_test_tasks

        with patch.dict(self.app.config, {'USE_CELERY_TASKS': True}):
            with self.app.app_context():
                # Should return early without error
                trigger_test_tasks([], 'fake_token')

    def test_trigger_test_tasks_handles_import_error(self):
        """Test graceful handling when Celery module is not available."""
        from mod_ci.controllers import trigger_test_tasks

        with patch.dict(self.app.config, {'USE_CELERY_TASKS': True}):
            # Simulate import error by patching the import
            with patch.dict('sys.modules', {'mod_ci.tasks': None}):
                with self.app.app_context():
                    # Should not raise exception
                    trigger_test_tasks([1, 2], 'fake_token')


class TestAddTestEntryReturnsIds(BaseTestCase):
    """Test that add_test_entry returns test IDs correctly."""

    @mock.patch('mod_ci.controllers.g')
    @mock.patch('mod_ci.controllers.safe_db_commit')
    @mock.patch('mod_ci.controllers.Fork')
    @mock.patch('mod_ci.controllers.Test')
    def test_add_test_entry_returns_test_ids(self, mock_test, mock_fork, mock_commit, mock_g):
        """Test that add_test_entry returns list of created test IDs."""
        from mod_ci.controllers import add_test_entry

        # Setup mocks
        mock_g.github = {'repository_owner': 'test', 'repository': 'test'}
        mock_fork_obj = MagicMock()
        mock_fork_obj.id = 1
        mock_fork.query.filter.return_value.first.return_value = mock_fork_obj
        mock_commit.return_value = True

        # Setup mock Test objects to return IDs
        mock_linux_test = MagicMock()
        mock_linux_test.id = 100
        mock_windows_test = MagicMock()
        mock_windows_test.id = 101
        mock_test.side_effect = [mock_linux_test, mock_windows_test]

        mock_db = MagicMock()

        # Call the function with a valid commit hash (40 hex chars)
        test_ids = add_test_entry(mock_db, 'a' * 40, TestType.commit)

        # Verify we got a list with 2 IDs
        self.assertIsInstance(test_ids, list)
        self.assertEqual(len(test_ids), 2)
        self.assertEqual(test_ids[0], 100)
        self.assertEqual(test_ids[1], 101)

    def test_add_test_entry_invalid_commit_returns_empty(self):
        """Test that invalid commit hash returns empty list."""
        from mod_ci.controllers import add_test_entry

        mock_db = MagicMock()

        # Call with invalid commit hash
        test_ids = add_test_entry(mock_db, 'invalid_hash', TestType.commit)

        # Verify empty list for invalid commit
        self.assertIsInstance(test_ids, list)
        self.assertEqual(len(test_ids), 0)

    @mock.patch('mod_ci.controllers.g')
    @mock.patch('mod_ci.controllers.safe_db_commit')
    @mock.patch('mod_ci.controllers.Fork')
    @mock.patch('mod_ci.controllers.Test')
    def test_add_test_entry_db_failure_returns_empty(self, mock_test, mock_fork, mock_commit, mock_g):
        """Test that db commit failure returns empty list."""
        from mod_ci.controllers import add_test_entry

        # Setup mocks
        mock_g.github = {'repository_owner': 'test', 'repository': 'test'}
        mock_fork_obj = MagicMock()
        mock_fork_obj.id = 1
        mock_fork.query.filter.return_value.first.return_value = mock_fork_obj
        mock_commit.return_value = False  # Simulate commit failure

        mock_linux_test = MagicMock()
        mock_linux_test.id = 100
        mock_windows_test = MagicMock()
        mock_windows_test.id = 101
        mock_test.side_effect = [mock_linux_test, mock_windows_test]

        mock_db = MagicMock()

        # Call the function
        test_ids = add_test_entry(mock_db, 'a' * 40, TestType.commit)

        # Verify empty list when commit fails
        self.assertIsInstance(test_ids, list)
        self.assertEqual(len(test_ids), 0)


if __name__ == '__main__':
    unittest.main()
