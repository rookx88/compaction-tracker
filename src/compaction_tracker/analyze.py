from __future__ import annotations

import argparse
import json
from pathlib import Path

from compaction_tracker.core import analyze_session_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate OpenClaw compaction overhead from a session JSONL")
    parser.add_argument("--session", required=True, help="Path to session JSONL file")
    parser.add_argument("--pretty", action="store_true", help="Print human-readable summary")
    args = parser.parse_args()

    result = analyze_session_file(Path(args.session))

    if not args.pretty:
        print(json.dumps(result, indent=2))
        return

    print(f"Total compactions found: {result['compactionCount']}")
    print(f"Scored compactions: {result['scoredCompactions']}")
    print(f"Estimated compaction overhead tokens: {result['estimatedCompactionTokens']}")
    print(f"Estimated USD cost: ${result['estimatedUSD']:.6f}")
    print("Per-event breakdown:")
    for i, ev in enumerate(result["perEvent"], start=1):
        print(
            f"  {i}. {ev.get('timestamp')} | tokensBefore={ev.get('tokensBefore')} | "
            f"preAvg={ev.get('preAverageInputTokens')} | post={ev.get('postInputTokens')} | "
            f"delta={ev.get('deltaTokens')} | {ev.get('notes')}"
        )


if __name__ == "__main__":
    main()
