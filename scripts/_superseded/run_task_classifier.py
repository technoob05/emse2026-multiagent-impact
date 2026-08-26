from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.task_classifier import run_task_classification  # noqa: E402


if __name__ == "__main__":
    config = AnalysisConfig.from_paths(PROJECT_ROOT)
    result = run_task_classification(
        config.data_dir, config.output_dir / "specialization"
    )
    for evaluation in result["evaluations"]:
        print(
            f"{evaluation['split']}: accuracy={evaluation['accuracy']:.3f}, "
            f"macro-F1={evaluation['macro_f1']:.3f}, n={evaluation['test_n']:,}"
        )
    print(f"Predicted rows: {result['prediction_rows']:,}")
