"""Triage helpers: turn raw RunSample results into classified failure rows.

Shared by ``sp run failures`` and ``sp investigate`` so both label failures the
same way. The classification itself lives in :mod:`sp_cli.classifier`; this module
adapts a ``RunSample`` (from ``/runs/{id}/samples``) into a flat, agent-friendly row.
"""

from typing import Any, Dict, List

from sp_cli.classifier import classify

#: RunSample statuses that count as a failure worth triaging.
FAILURE_STATUSES = ('fail', 'missing_output')


def is_failure(sample: Dict[str, Any]) -> bool:
    """
    Report whether a RunSample result is a failure.

    :param sample: One ``RunSample`` object.
    :type sample: Dict[str, Any]
    :return: True if the result failed or produced no output.
    :rtype: bool
    """
    return sample.get('status') in FAILURE_STATUSES


def has_output_diff(sample: Dict[str, Any]) -> bool:
    """
    Decide whether a failing sample recorded a differing output file.

    Prefers the per-output ``status`` when present; otherwise falls back to
    "failed but the exit code matched, so the failure must be an output diff."

    :param sample: One ``RunSample`` object.
    :type sample: Dict[str, Any]
    :return: True if an output differed from expected.
    :rtype: bool
    """
    outputs = sample.get('outputs') or []
    if outputs:
        return any(item.get('status') not in (None, 'pass') for item in outputs)
    return sample.get('status') == 'fail' and sample.get('exit_code') == sample.get('expected_rc')


def classify_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a RunSample result onto a classified failure row.

    :param sample: One ``RunSample`` object from ``/runs/{id}/samples``.
    :type sample: Dict[str, Any]
    :return: A flat row with ids plus the classification code, confidence and reason.
    :rtype: Dict[str, Any]
    """
    label = classify(
        sample.get('exit_code'), sample.get('expected_rc'),
        missing_output=(sample.get('status') == 'missing_output'),
        has_output_diff=has_output_diff(sample),
    )
    return {
        'regression_test_id': sample.get('regression_test_id'),
        'sample_id': sample.get('sample_id'),
        'sample_name': sample.get('sample_name'),
        'categories': sample.get('categories') or [],
        'exit_code': sample.get('exit_code'),
        'expected_rc': sample.get('expected_rc'),
        'code': label['code'],
        'confidence': label['confidence'],
        'reason': label['reason'],
    }


def group_by_code(failures: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Count classified failures by their code.

    :param failures: Classified failure rows.
    :type failures: List[Dict[str, Any]]
    :return: A mapping of code → count, highest first.
    :rtype: Dict[str, int]
    """
    counts: Dict[str, int] = {}
    for failure in failures:
        counts[failure['code']] = counts.get(failure['code'], 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))
