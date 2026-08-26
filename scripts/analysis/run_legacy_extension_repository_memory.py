"""Run the retained legacy-inspired repository-memory extensions.

This entry point keeps all extension outputs below ``outputs/_superseded/legacy_extensions``
while reusing the independently testable analysis modules.
"""

from pathlib import Path

import run_human_memory_bridge_analysis as bridge
import run_review_request_context_analysis as requests


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "legacy_extensions"


def main() -> None:
    bridge.OUTPUT = OUTPUT / "repository_memory"
    requests.OUTPUT = OUTPUT / "review_request_context"
    bridge.main()
    requests.main()


if __name__ == "__main__":
    main()
