"""Handle all the custom exceptions raised."""
import sys


class QueuedSampleNotFoundException(Exception):
    """Custom exception handler for queued sample not found."""

    def __init__(self, message: str) -> None:
        Exception.__init__(self)
        self.message = message


class SampleNotFoundException(Exception):
    """Custom exception triggered when sample not found."""

    def __init__(self, message: str) -> None:
        Exception.__init__(self)
        self.message = message


class TestNotFoundException(Exception):
    """Custom exception handler for handling test not found."""

    def __init__(self, message: str) -> None:
        Exception.__init__(self)
        self.message = message


class SecretKeyInstallationException(Exception):
    """Custom exception handler for handling failed installation of secret keys."""

    def __init__(self) -> None:
        Exception.__init__(self)
        sys.exit(1)


class IncompleteConfigException(Exception):
    """Custom exception handler for handling missing configuration errors."""

    pass


class MissingConfigError(Exception):
    """Custom exception handler for handling missing config.py file."""

    pass
