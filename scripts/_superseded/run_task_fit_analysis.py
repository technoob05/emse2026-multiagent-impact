from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.specialization import load_labelled_pull_requests  # noqa: E402
from multiagent_impact.task_fit import (  # noqa: E402
    analyze_task_fit,
    build_task_fit_sample,
    save_task_fit_results,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test time-safe historical task-agent fit in multi-agent repositories"
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--min-pair-history", type=int, default=20)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    config = AnalysisConfig.from_paths(args.project_root, args.data_dir)
    frame = load_labelled_pull_requests(config.data_dir)
    sample = build_task_fit_sample(frame, min_pair_history=args.min_pair_history)
    results = analyze_task_fit(sample)
    save_task_fit_results(sample, results, config.output_dir / "specialization")
    print(f"Eligible PRs: {results['eligible_pull_requests']:,}")
    print(f"Repositories: {results.get('repositories', 0):,}")
    if results["eligible_pull_requests"]:
        term = results["adjusted_with_repo_fixed_effects"]["terms"].get(
            "best_task_fit", {}
        )
        print(
            "Adjusted best-fit difference: "
            f"{term.get('estimate', float('nan')):.3f} "
            f"(p={term.get('p', float('nan')):.4f})"
        )
