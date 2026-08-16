"""Compare one test run's regression results against another run's.

Pass and fail are decided elsewhere, and against one thing only: the approved
output. That answers "is this correct?", which is the question a baseline is for
-- but it is not the question a reviewer is asking. A reviewer wants to know
what *this change* did, and a test that has been failing since last month tells
them nothing while burying the one that started failing today.

So the verdict stays absolute and the report is relative. The same failure is
described against several references at once: the approved output, the tip of
master, and the closest ancestor commit we still hold results for. A test
failing identically on all of them is drift someone needs to approve; a test
failing only here is the change under review.

The functions below take plain values rather than models so the classification
can be tested without a database, a GitHub client, or a CI run.
"""

from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

#: The test matched the approved output on both sides.
UNCHANGED_PASS = 'unchanged_pass'
#: Fails here, matched the approved output in the reference run.
BROKEN_HERE = 'broken_here'
#: Matches the approved output here, failed in the reference run.
FIXED_HERE = 'fixed_here'
#: Fails on both sides and produces the *same* bytes -- unchanged behaviour
#: measured against a baseline that no longer describes it.
FAILING_IDENTICALLY = 'failing_identically'
#: Fails on both sides but the output differs, so something moved even though
#: the verdict did not.
FAILING_DIFFERENTLY = 'failing_differently'
#: The reference run holds no record of this test, so nothing can be said.
NO_REFERENCE = 'no_reference'

#: Every verdict, in the order a reader should be shown them: what this change
#: broke first, what it fixed next, then the pre-existing noise.
VERDICTS = (BROKEN_HERE, FIXED_HERE, FAILING_DIFFERENTLY, FAILING_IDENTICALLY,
            UNCHANGED_PASS, NO_REFERENCE)


class TestState(NamedTuple):
    """How one regression test behaved in one run.

    ``signature`` identifies *how* a failing test differed, so two runs failing
    the same test can be told apart by whether they produced the same bytes.
    """

    #: True when the exit code matched and every output file matched the approved one.
    passed: bool
    #: (output_id, produced hash) for each output that did not match, sorted.
    signature: Tuple[Tuple[int, Optional[str]], ...]


def build_state(test_results: Iterable[Any]) -> Dict[int, TestState]:
    """
    Summarise a run as one state per regression test.

    Whether a test passed is taken from ``get_test_results``, which is the
    platform's own verdict and already accounts for exit codes, outputs that are
    absent when they should not be, and the alternative hashes an output may
    legitimately produce. Re-deriving any of that here would mean two
    definitions of "passed" that could drift apart.

    The signature is built from the recorded hashes, which is the part
    ``get_test_results`` does not express: it lets two runs failing the same
    test be told apart by whether they produced the same bytes.

    :param test_results: The structure returned by ``get_test_results``.
    :type test_results: Iterable[Any]
    :return: Regression test id mapped to how that test behaved.
    :rtype: Dict[int, TestState]
    """
    states: Dict[int, TestState] = {}
    for category in test_results:
        for entry in category['tests']:
            # A caller that reports no files leaves the failure unexplained rather
            # than unnoticed: the verdict still counts, only the signature is empty.
            failed_outputs: List[Tuple[int, Optional[str]]] = sorted(
                (result_file.regression_test_output_id, result_file.got)
                for result_file in (entry.get('files') or ()) if result_file.got is not None)
            states[entry['test'].id] = TestState(passed=not entry['error'],
                                                 signature=tuple(failed_outputs))
    return states


def classify(current: TestState, reference: Optional[TestState]) -> str:
    """
    Describe one test's behaviour here relative to a reference run.

    :param current: How the test behaved in the run being reported on.
    :type current: TestState
    :param reference: How it behaved in the reference run, if that run has a record.
    :type reference: Optional[TestState]
    :return: One of the module's verdict constants.
    :rtype: str
    """
    if reference is None:
        return NO_REFERENCE
    if current.passed and reference.passed:
        return UNCHANGED_PASS
    if current.passed:
        return FIXED_HERE
    if reference.passed:
        return BROKEN_HERE
    if current.signature == reference.signature:
        return FAILING_IDENTICALLY
    return FAILING_DIFFERENTLY


def compare(current: Dict[int, TestState],
            reference: Optional[Dict[int, TestState]]) -> Dict[str, List[int]]:
    """
    Bucket every regression test in a run by how it compares to a reference run.

    A missing reference run is not the same as a reference run that passed
    everything: it is reported as ``no_reference`` so the comment can say "we
    have no records to compare against" instead of implying good news.

    :param current: States for the run being reported on.
    :type current: Dict[int, TestState]
    :param reference: States for the reference run, or None when there is no such run.
    :type reference: Optional[Dict[int, TestState]]
    :return: Verdict mapped to the regression test ids in it.
    :rtype: Dict[str, List[int]]
    """
    buckets: Dict[str, List[int]] = {verdict: [] for verdict in VERDICTS}
    for rt_id in sorted(current):
        reference_state = None if reference is None else reference.get(rt_id)
        buckets[classify(current[rt_id], reference_state)].append(rt_id)
    return buckets


def summarise(buckets: Dict[str, List[int]]) -> Dict[str, int]:
    """
    Count each verdict, for a table that has to stay short.

    :param buckets: Output of :func:`compare`.
    :type buckets: Dict[str, List[int]]
    :return: Verdict mapped to how many tests fell in it.
    :rtype: Dict[str, int]
    """
    return {verdict: len(ids) for verdict, ids in buckets.items()}
