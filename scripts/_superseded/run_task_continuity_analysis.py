from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.task_continuity import run  # noqa: E402


if __name__ == "__main__":
    config = AnalysisConfig.from_paths(ROOT)
    run(
        ROOT / "outputs" / "cache" / "latest_resolved_transitions.parquet",
        config.data_dir / "all_pull_request.parquet",
        ROOT / "outputs" / "handoff_exploration" / "artifact_handoff_episodes.parquet",
        ROOT / "outputs" / "task_continuity_exploration",
    )
