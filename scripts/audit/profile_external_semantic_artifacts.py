"""Emit the deterministic, aggregate-only external semantic source audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from external_validation.semantic_artifacts import build_profile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--swe-root",
        type=Path,
        default=ROOT / "external_data" / "downloads" / "swe-prbench",
    )
    parser.add_argument(
        "--review-action-archive",
        type=Path,
        default=(
            ROOT
            / "external_data"
            / "downloads"
            / "zenodo-19562450"
            / "AIReviewActionAnalysis.zip"
        ),
    )
    parser.add_argument(
        "--aidev-root",
        type=Path,
        default=WORKSPACE / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    profile = build_profile(
        swe_root=args.swe_root,
        review_action_archive=args.review_action_archive,
        aidev_root=args.aidev_root,
    )
    rendered = json.dumps(profile, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
