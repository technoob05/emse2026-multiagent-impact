from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.matched_adoption import (  # noqa: E402
    MatchedAdoptionConfig,
    run_matched_adoption,
)


if __name__ == "__main__":
    common = AnalysisConfig.from_paths(PROJECT_ROOT)
    config = MatchedAdoptionConfig(
        data_dir=common.data_dir,
        output_dir=common.output_dir / "matched_adoption",
    )
    result = run_matched_adoption(config)
    print(f"Matched pairs: {result['matched_pairs']:,}")
    print(f"Pre-trend gate passed: {result['causal_gate_passed']}")
    print(f"Mean post-entry log-PR contrast: {result['post_mean_log_pr']:.3f}")
    print(f"Mean post-entry PR-count contrast: {result['post_mean_pr_count']:.2f}")
    print(f"Mean post-entry merged-count contrast: {result['post_mean_merged_count']:.2f}")
