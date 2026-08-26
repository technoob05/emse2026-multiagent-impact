from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.direct_handoff import run  # noqa: E402
from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402


if __name__ == "__main__":
    config = AnalysisConfig.from_paths(ROOT)
    run(
        config.data_dir,
        ROOT / "outputs" / "tables",
        ROOT / "outputs" / "figures",
        ROOT / "outputs" / "cache",
    )
