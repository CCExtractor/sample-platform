"""Handle all the custom exceptions raised."""


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
