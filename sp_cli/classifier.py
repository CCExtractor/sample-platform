"""Rule-based classification of regression-test failures into stable codes.

Deterministic, no ML: maps the raw signals a test run exposes (exit code,
expected return code, output presence, pass-history) onto a small, stable
taxonomy so an agent can branch on *why* a test failed instead of parsing
prose. Platform differences are normalized — e.g. a segfault surfaces as ``139``
on Linux and ``-1073741819`` (0xC0000005) on Windows; both classify as
``SEGFAULT``.

Each classification returns a ``code`` (stable, machine-readable), a
``confidence`` (``high`` for unambiguous exit-code rules, ``medium`` for
output-based ones), a human ``reason``, and ``regression`` (True if the test was
passing before — a real regression; False if it never passed; None if unknown).
"""

from typing import Any, Dict, Optional

# --- Failure codes (stable; downstream tools may pin on these) ---------------
CODE_PASS = "PASS"
CODE_SEGFAULT = "SEGFAULT"
CODE_ABORT = "ABORT"
CODE_TIMEOUT = "TIMEOUT"
CODE_MISSING_OUTPUT = "MISSING_OUTPUT"
CODE_EXIT_CODE_MISMATCH = "EXIT_CODE_MISMATCH"
CODE_OUTPUT_DIFF = "OUTPUT_DIFF"
CODE_UNKNOWN = "UNKNOWN"

# --- Exit codes that denote a crash, normalized across platforms -------------
#: SIGSEGV (128+11) on Linux, raw -11, and 0xC0000005 access violation on Windows.
_SEGFAULT_CODES = frozenset({139, -11, -1073741819})
#: SIGABRT (128+6) on Linux and raw -6.
_ABORT_CODES = frozenset({134, -6})
#: `timeout` exit (124) and SIGTERM (143 / -15).
_TIMEOUT_CODES = frozenset({124, 143, -15})


def classify(exit_code: Optional[int], expected_rc: Optional[int], *,
             has_output_diff: bool = False, missing_output: bool = False,
             has_ever_passed: Optional[bool] = None) -> Dict[str, Any]:
    """
    Classify a single regression-test result into a stable failure code.

    Rules are evaluated most-severe first (crash > timeout > missing output >
    exit-code mismatch > output diff), so the most actionable signal wins.

    :param exit_code: The process exit code observed for the test.
    :type exit_code: Optional[int]
    :param expected_rc: The exit code the test was expected to return.
    :type expected_rc: Optional[int]
    :param has_output_diff: True if a differing output file was recorded.
    :type has_output_diff: bool
    :param missing_output: True if output was expected but none was produced.
    :type missing_output: bool
    :param has_ever_passed: Whether this test has ever passed (history), if known.
    :type has_ever_passed: Optional[bool]
    :return: ``{code, confidence, reason, regression}``.
    :rtype: Dict[str, Any]
    """
    regression = _regression_state(has_ever_passed)

    if exit_code in _SEGFAULT_CODES:
        return _result(CODE_SEGFAULT, "high",
                       f"Crash (segfault / access violation), exit {exit_code}", regression)
    if exit_code in _ABORT_CODES:
        return _result(CODE_ABORT, "high", f"Aborted (SIGABRT), exit {exit_code}", regression)
    if exit_code in _TIMEOUT_CODES:
        return _result(CODE_TIMEOUT, "high", f"Timed out / terminated, exit {exit_code}", regression)
    if missing_output:
        return _result(CODE_MISSING_OUTPUT, "high",
                       "No output was produced but one was expected", regression)
    if exit_code != expected_rc:
        return _result(CODE_EXIT_CODE_MISMATCH, "high",
                       f"Exited {exit_code}, expected {expected_rc}", regression)
    if has_output_diff:
        return _result(CODE_OUTPUT_DIFF, "medium",
                       "Exit code matched but output differs from expected", regression)

    return _result(CODE_PASS, "high", "Exit code matched and no output diff recorded", regression)


def _regression_state(has_ever_passed: Optional[bool]) -> Optional[bool]:
    """
    Translate pass-history into the ``regression`` flag.

    :param has_ever_passed: Whether the test has ever passed, if known.
    :type has_ever_passed: Optional[bool]
    :return: True if a real regression, False if never worked, None if unknown.
    :rtype: Optional[bool]
    """
    if has_ever_passed is None:
        return None
    return bool(has_ever_passed)


def _result(code: str, confidence: str, reason: str, regression: Optional[bool]) -> Dict[str, Any]:
    """
    Assemble a classification result dict.

    :param code: The stable failure code.
    :type code: str
    :param confidence: ``high`` or ``medium``.
    :type confidence: str
    :param reason: Human-readable explanation.
    :type reason: str
    :param regression: Regression flag (see :func:`_regression_state`).
    :type regression: Optional[bool]
    :return: The assembled result.
    :rtype: Dict[str, Any]
    """
    return {"code": code, "confidence": confidence, "reason": reason, "regression": regression}
