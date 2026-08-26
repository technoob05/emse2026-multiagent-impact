from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "02_artifact_handoff_exploration.ipynb"


def markdown(value: str):
    return nbf.v4.new_markdown_cell(dedent(value).strip())


def code(value: str):
    return nbf.v4.new_code_cell(dedent(value).strip())


cells = [
    markdown(
        """
        # From co-presence to coordination

        ## Main lesson

        Temporal order, a shared file, the same task, and coordination are
        different constructs. This notebook shows how the candidate set narrows
        as the evidence becomes stronger. It does not estimate true handoff
        prevalence, and the AI-assisted screen is not human ground truth.
        """
    ),
    code(
        """
        from pathlib import Path
        import pandas as pd
        from IPython.display import Image, display

        ROOT = Path.cwd()
        if ROOT.name == "notebooks":
            ROOT = ROOT.parent
        TABLES = ROOT / "outputs" / "tables"
        FIGURES = ROOT / "outputs" / "figures"
        CACHE = ROOT / "outputs" / "cache"

        required = [
            TABLES / "direct_continuity_funnel.csv",
            TABLES / "direct_continuity_composition.csv",
            TABLES / "direct_continuity_threshold_sensitivity.csv",
            TABLES / "direct_continuity_screen_diagnostic.csv",
            CACHE / "direct_continuity_candidates.parquet",
            FIGURES / "direct_continuation_funnel.png",
        ]
        missing = [str(path) for path in required if not path.exists()]
        assert not missing, f"Run scripts/analysis/run_direct_continuity_analysis.py; missing: {missing}"
        """
    ),
    markdown("## RQ1 -- Measurement funnel"),
    code(
        """
        funnel = pd.read_csv(TABLES / "direct_continuity_funnel.csv")
        shown = funnel.copy()
        shown["share_of_eligible"] = shown["share_of_eligible"].map(lambda value: f"{value:.1%}")
        display(shown)
        display(Image(filename=str(FIGURES / "direct_continuation_funnel.png")))
        """
    ),
    markdown(
        """
        An exact-file successor is a candidate generator, not a same-task label.
        The strong rule uses shared issue evidence or title similarity of at
        least 0.20. It was chosen after a pre-audit and needs held-out human
        validation.
        """
    ),
    markdown("## RQ2 -- Proxy diagnostic"),
    code(
        """
        diagnostic = pd.read_csv(TABLES / "direct_continuity_screen_diagnostic.csv")
        shown = diagnostic[[
            "title_threshold", "selected_n", "true_positive_n",
            "false_positive_n", "false_negative_n", "screen_precision",
            "screen_recall", "title_score_auc", "validation_status"
        ]].copy()
        shown["screen_precision"] = shown["screen_precision"].map(lambda value: f"{value:.1%}")
        shown["screen_recall"] = shown["screen_recall"].map(lambda value: f"{value:.1%}")
        shown["title_score_auc"] = shown["title_score_auc"].map(lambda value: f"{value:.3f}")
        display(shown)
        """
    ),
    markdown(
        """
        The diagnostic uses 9 consensus-positive and 73 consensus-negative
        endpoints from two AI-assisted screens. Since the screens also used
        titles, the AUC is not an independent classifier result. Its purpose is
        to design the human study.
        """
    ),
    markdown("## RQ3 -- Does the multi-agent story survive stricter rules?"),
    code(
        """
        sensitivity = pd.read_csv(TABLES / "direct_continuity_threshold_sensitivity.csv")
        shown = sensitivity.copy()
        shown["candidate_share_of_exact_file"] = shown["candidate_share_of_exact_file"].map(lambda value: f"{value:.1%}")
        display(shown)
        """
    ),
    markdown(
        """
        The exact candidate count changes with the threshold, but one result is
        stable: cross-agent continuation candidates are a small subset, and most
        also change contributor. The old merge flag is only later-successor
        integration by a common deadline; it is not failed-task recovery.

        ## Next gate

        Run `scripts/audit/build_human_audit_packets.py`, complete both blinded coder
        files, report agreement and adjudication, then validate the rule on a
        held-out set. Do not make an agent-effect claim before this step.
        """
    ),
]

notebook = nbf.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
)
NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
nbf.write(notebook, NOTEBOOK)
print(NOTEBOOK)
