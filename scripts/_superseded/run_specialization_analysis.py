from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.specialization import (  # noqa: E402
    SpecializationConfig,
    build_specialization_cohorts,
    load_labelled_pull_requests,
    save_specialization_results,
    summarize_specialization,
    validate_title_labels,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test whether a repository's second AI agent adds task specialization"
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--permutations", type=int, default=2_000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    common = AnalysisConfig.from_paths(args.project_root, args.data_dir)
    config = SpecializationConfig(
        data_dir=common.data_dir,
        output_dir=common.output_dir / "specialization",
        pre_days=args.window_days,
        post_days=args.window_days,
        permutations=args.permutations,
    )
    pull_requests = load_labelled_pull_requests(config.data_dir)
    audit = validate_title_labels(pull_requests, config.data_dir)
    cohorts, pooled_post = build_specialization_cohorts(pull_requests, config)
    summary = summarize_specialization(cohorts, pooled_post, config)
    save_specialization_results(config, audit, cohorts, summary)
    print(f"Labelled PRs: {audit['rule_labelled']:,}")
    print(f"Label agreement: {audit['agreement']:.3f}")
    print(f"Eligible repositories: {summary['eligible_repositories']:,}")
    if summary["eligible_repositories"]:
        print(
            "Entrant rarity advantage: "
            f"{summary['mean_rarity_difference']:.3f} "
            f"(paired sign-flip p={summary['paired_sign_flip_test']['p_two_sided']:.4f})"
        )
