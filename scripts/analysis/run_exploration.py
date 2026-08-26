from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig, run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AIDev v5 multi-agent exploration")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--event-window", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    config = AnalysisConfig.from_paths(
        project_root=args.project_root,
        data_dir=args.data_dir,
        event_window=args.event_window,
    )
    run_pipeline(config)
