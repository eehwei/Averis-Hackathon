#!/usr/bin/env python3
"""Sanity check: classify a slice of the inbox and print the predictions.

Run this before the full inbox so a broken loader path, a bad model id or a
missing API key shows up after a handful of cheap calls instead of 520.

    python scripts/run_classify_submission.py                    # first 10
    python scripts/run_classify_submission.py --sample 20        # 20 at random
    python scripts/run_classify_submission.py --sample 20 --seed 42

--sample is seeded, so the same seed always picks the same emails. Use that to
re-score an identical set after a prompt change.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "sdoc-hackathon-bundle"

for _path in (ROOT / "src", BUNDLE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from classify import MODEL, classify_email  # noqa: E402
from loader import Inbox  # noqa: E402


def _classify(email: dict) -> tuple[dict, str, bool]:
    try:
        return email, classify_email(email), True
    except Exception as exc:  # keep going so one bad call can't hide the rest
        # Show the real error text, not just the exception type, so failures
        # are actually diagnosable from the table instead of guessing.
        message = str(exc)[:120]
        return email, f"ERROR ({type(exc).__name__}: {message})", False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify a slice of the inbox and print the predictions."
    )
    parser.add_argument(
        "--source",
        default=str(BUNDLE),
        help="bundle folder holding inbox/ and attachments/, or a server URL",
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="classify the first N emails (default: 10)"
    )
    parser.add_argument(
        "--sample", type=int, help="instead, classify N emails chosen at random"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="seed for --sample (default: 42)"
    )
    parser.add_argument(
        "--workers", type=int, default=5, help="parallel API calls (default: 5)"
    )
    args = parser.parse_args()

    emails = Inbox(args.source).emails()

    if args.sample:
        chosen = random.Random(args.seed).sample(emails, min(args.sample, len(emails)))
        chosen.sort(key=lambda e: e["email_id"])
        how = f"{len(chosen)} at random (seed {args.seed})"
    else:
        chosen = emails[: args.limit]
        how = f"the first {len(chosen)}"

    print(f"Classifying {how} of {len(emails)} emails with {MODEL}\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_classify, chosen))

    tally: Counter = Counter()
    failures = 0

    print(f"{'#':>3}  {'id':<11} {'att':>3}  predicted / subject")
    print("-" * 100)
    for i, (email, category, ok) in enumerate(results, start=1):
        tally[category] += 1
        failures += not ok
        print(
            f"{i:>3}  {email['email_id']:<11} {len(email['attachments']):>3}  "
            f"{category}"
        )
        print(f"{'':>3}  {'':<11} {'':>3}  subject: {email['subject'][:80]}")
        body = " ".join(email["body"].split())
        print(f"{'':>3}  {'':<11} {'':>3}  > {body[:100]}")

    print("\nTally:")
    for category, count in tally.most_common():
        print(f"  {count:>3}  {category}")

    if failures:
        print(f"\n{failures} of {len(chosen)} calls failed - fix before the full run.")
        return 1

    print(f"\nAll {len(chosen)} classified. Full inbox is {len(emails)} emails.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())