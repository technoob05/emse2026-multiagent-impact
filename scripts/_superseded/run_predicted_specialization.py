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
    load_predicted_pull_requests,
    summarize_specialization,
)


if __name__ == "__main__":
    common = AnalysisConfig.from_paths(PROJECT_ROOT)
    output_dir = common.output_dir / "specialization"
    predictions = output_dir / "task_type_predictions.parquet"
    specifications = [
        (30, 0.0, 5, 5, 3),
        (60, 0.0, 5, 5, 3),
        (90, 0.0, 5, 5, 3),
        (120, 0.0, 5, 5, 3),
        (90, 0.5, 5, 5, 3),
        (90, 1.0, 5, 5, 3),
        (90, 0.0, 10, 10, 5),
        (90, 0.0, 20, 20, 5),
    ]
    cached_frames = {}
    results = []
    baseline_cohort = None
    for index, (window, margin, min_pre, min_post, min_entrant) in enumerate(
        specifications
    ):
        if margin not in cached_frames:
            cached_frames[margin] = load_predicted_pull_requests(
                common.data_dir, predictions, min_margin=margin
            )
        config = SpecializationConfig(
            data_dir=common.data_dir,
            output_dir=output_dir,
            pre_days=window,
            post_days=window,
            min_pre=min_pre,
            min_post=min_post,
            min_entrant=min_entrant,
            permutations=2_000 if index == 2 else 500,
            seed=20260825 + index * 10,
        )
        cohort, pooled = build_specialization_cohorts(cached_frames[margin], config)
        summary = summarize_specialization(cohort, pooled, config)
        results.append(
            {
                "window_days": window,
                "min_margin": margin,
                "min_pre": min_pre,
                "min_post": min_post,
                "min_entrant": min_entrant,
                **summary,
            }
        )
        if index == 2:
            baseline_cohort = cohort
        print(
            f"window={window}, margin={margin}, minima={min_pre}/{min_post}/{min_entrant}: "
            f"repos={summary['eligible_repositories']}, "
            f"difference={summary.get('mean_rarity_difference', float('nan')):.3f}, "
            f"p={summary.get('paired_sign_flip_test', {}).get('p_two_sided', float('nan')):.4f}"
        )
    with (output_dir / "predicted_specialization_sensitivity.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)
    if baseline_cohort is not None:
        baseline_cohort.to_csv(
            output_dir / "predicted_specialization_repository_cohorts.csv", index=False
        )
        with (output_dir / "predicted_specialization_summary.json").open(
            "w", encoding="utf-8"
        ) as handle:
            json.dump(results[2], handle, indent=2, ensure_ascii=False)
