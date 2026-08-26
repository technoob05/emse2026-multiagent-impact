from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.streak_analysis import (  # noqa: E402
    StreakConfig,
    run_streak_analysis,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run canonical AIDev non-integration streak analysis"
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_streak_analysis(
        StreakConfig.from_paths(
            project_root=args.project_root,
            data_dir=args.data_dir,
        )
    )
