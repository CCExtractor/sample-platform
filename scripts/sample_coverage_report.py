from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set

from mod_regression.sample_inventory import inventory_samples


def build_coverage(inventory: List[dict]) -> dict:
    containers = Counter()
    captions = Counter()
    matrix: Dict[str, Counter] = defaultdict(Counter)

    for item in inventory:
        container = item.get("container") or "unknown"
        containers[container] += 1

        cap_types = item.get("caption_types_detected") or []
        if not cap_types:
            captions["none"] += 1
            matrix[container]["none"] += 1
            continue

        for c in cap_types:
            captions[c] += 1
            matrix[container][c] += 1

    return {
        "total_samples": len(inventory),
        "containers": dict(containers),
        "captions": dict(captions),
        "matrix": {k: dict(v) for k, v in matrix.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample coverage report")
    parser.add_argument("sample_root", type=Path, help="Root directory containing samples")
    parser.add_argument("--json-out", type=Path, default=None, help="Write report as JSON to this path")
    args = parser.parse_args()

    inv = inventory_samples(args.sample_root)
    report = build_coverage(inv)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Human-friendly summary
    print(f"Total samples: {report['total_samples']}")
    print("\nContainer coverage:")
    for k, v in sorted(report["containers"].items(), key=lambda x: (-x[1], x[0])):
        print(f"  {k}: {v}")

    print("\nCaption-type coverage:")
    for k, v in sorted(report["captions"].items(), key=lambda x: (-x[1], x[0])):
        print(f"  {k}: {v}")

    print("\nContainer x Caption matrix (counts):")
    for container, caps in sorted(report["matrix"].items()):
        caps_str = ", ".join(f"{c}={n}" for c, n in sorted(caps.items()))
        print(f"  {container}: {caps_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
