from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.contributor_analysis import run  # noqa: E402


if __name__ == "__main__":
    run(
        ROOT / "outputs" / "cache" / "latest_resolved_transitions.parquet",
        ROOT / "outputs" / "tables",
        ROOT / "outputs" / "figures",
    )
