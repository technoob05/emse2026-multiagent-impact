from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.specialization import (  # noqa: E402
    SpecializationConfig,
    build_specialization_cohorts,
    load_labelled_pull_requests,
    summarize_specialization,
)


if __name__ == "__main__":
    common = AnalysisConfig.from_paths(PROJECT_ROOT)
    frame = load_labelled_pull_requests(common.data_dir)
    specifications = [
        (30, 5, 5, 3),
        (60, 5, 5, 3),
        (90, 5, 5, 3),
        (120, 5, 5, 3),
        (90, 10, 10, 3),
        (90, 20, 20, 5),
    ]
    results = []
    for index, (window, min_pre, min_post, min_entrant) in enumerate(specifications):
        config = SpecializationConfig(
            data_dir=common.data_dir,
            output_dir=common.output_dir / "specialization",
            pre_days=window,
            post_days=window,
            min_pre=min_pre,
            min_post=min_post,
            min_entrant=min_entrant,
            permutations=500,
            seed=20260825 + index * 10,
        )
        cohort, pooled = build_specialization_cohorts(frame, config)
        summary = summarize_specialization(cohort, pooled, config)
        results.append(
            {
                "window_days": window,
                "min_pre": min_pre,
                "min_post": min_post,
                "min_entrant": min_entrant,
                **summary,
            }
        )
        print(
            f"window={window}, minima={min_pre}/{min_post}/{min_entrant}: "
            f"repos={summary['eligible_repositories']}, "
            f"difference={summary.get('mean_rarity_difference', float('nan')):.3f}"
        )
    output = common.output_dir / "specialization" / "sensitivity.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)
