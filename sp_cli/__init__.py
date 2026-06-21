"""``sp`` — an AI-friendly command-line client for the CCExtractor Sample Platform.

The CLI is a thin layer over the Sample Platform JSON API (``/api/v1``). It is
designed to be driven by AI agents as well as humans: it emits machine-readable
JSON by default and uses non-zero exit codes plus a consistent error envelope on
failure, so it can be scripted without screen-scraping the web UI.
"""

__version__ = "0.1.0"
