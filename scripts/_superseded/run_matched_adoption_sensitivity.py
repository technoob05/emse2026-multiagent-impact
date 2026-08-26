from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.matched_adoption import (  # noqa: E402
    MatchedAdoptionConfig,
    build_event_contrasts,
    build_matched_pairs,
    load_monthly_panel,
    summarize_event_contrasts,
)
from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402


if __name__ == "__main__":
    common = AnalysisConfig.from_paths(PROJECT_ROOT)
    output_dir = common.output_dir / "matched_adoption"
    monthly, timing = load_monthly_panel(common.data_dir)
    specifications = [
        (0.50, True),
        (0.75, True),
        (1.00, True),
        (1.50, True),
        (0.75, False),
        (1.00, False),
        (1.50, False),
    ]
    results = []
    for distance, replacement in specifications:
        config = MatchedAdoptionConfig(
            data_dir=common.data_dir,
            output_dir=output_dir,
            max_match_distance=distance,
            match_with_replacement=replacement,
        )
        pairs = build_matched_pairs(monthly, timing, config)
        contrasts = build_event_contrasts(monthly, pairs, config)
        _, summary = summarize_event_contrasts(contrasts, pairs, config)
        results.append(
            {
                "max_match_distance": distance,
                "replacement": replacement,
                **summary,
            }
        )
        print(
            f"distance={distance:.2f}, replacement={replacement}: "
            f"pairs={summary['matched_pairs']}, pretrend={summary['causal_gate_passed']}, "
            f"post_log_pr={summary['post_mean_log_pr']:.3f}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "matched_adoption_sensitivity.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(results, handle, indent=2)
