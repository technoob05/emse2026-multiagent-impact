from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "01_multiagent_exploration.ipynb"


def markdown(text: str):
    return nbf.v4.new_markdown_cell(dedent(text).strip())


def code(text: str):
    return nbf.v4.new_code_cell(dedent(text).strip())


cells = [
    markdown(
        """
        # Multi-agent impact in AIDev v5

        **Purpose.** Reproduce the first evidence pass for three research questions: the
        sequential multi-agent onset, outcome-conditioned switching, and recovery after a
        closed-unmerged pull request. All estimates are exploratory associations.
        """
    ),
    markdown(
        """
        ## Context and method

        A transition links each mature current PR to the latest earlier PR in the same
        repository whose outcome was already known when the current PR opened. The primary
        ledger begins at observed second-agent entry, keeps the first current PR per prior
        episode, and measures merge within 30 days. The source dataset
        is pinned to Hugging Face revision
        `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`.
        """
    ),
    code(
        """
        from pathlib import Path
        import json
        import pandas as pd
        from IPython.display import Image, Markdown, display

        PROJECT_ROOT = Path.cwd()
        if PROJECT_ROOT.name == "notebooks":
            PROJECT_ROOT = PROJECT_ROOT.parent
        OUTPUT = PROJECT_ROOT / "outputs"
        TABLES = OUTPUT / "tables"
        FIGURES = OUTPUT / "figures"

        required = [
            TABLES / "data_quality.json",
            TABLES / "rq2_switching_response.csv",
            FIGURES / "rq2_switching_response.png",
        ]
        missing = [str(path) for path in required if not path.exists()]
        assert not missing, f"Run scripts/analysis/run_exploration.py first; missing: {missing}"
        """
    ),
    markdown("## Data quality and scope"),
    code(
        """
        quality = json.loads((TABLES / "data_quality.json").read_text(encoding="utf-8"))
        overview = pd.Series(quality["overview"], name="value").to_frame()
        display(overview)
        display(pd.DataFrame(quality["agent_counts"]))
        """
    ),
    markdown(
        """
        The corpus contains six labeled agents. Results should not be interpreted as a
        randomized comparison: repositories, tasks, contributor identities, and automation
        policies may jointly affect both agent switching and merge outcomes.
        """
    ),
    markdown("## RQ1 — How does sequential multi-agent participation begin?"),
    code(
        """
        event = pd.read_csv(TABLES / "rq1_event_study.csv")
        display(event)
        display(Image(filename=str(FIGURES / "rq1_event_study.png")))
        display(Image(filename=str(FIGURES / "rq1_transition_matrix.png")))
        """
    ),
    markdown(
        """
        The event profile is descriptive. The strong decline before second-agent entry shows
        endogenous timing and possible regression to the mean; the rebound is not an impact
        estimate. The transition matrix is topology evidence and belongs in an appendix.
        """
    ),
    markdown("## RQ2 — Does a closed-unmerged outcome precede agent switching?"),
    code(
        """
        switching = pd.read_csv(TABLES / "rq2_switching_response.csv")
        switching["switch_percent"] = 100 * switching["switch_rate"]
        display(switching[["prior_outcome", "n", "repositories", "switch_percent"]])
        display(Image(filename=str(FIGURES / "rq2_switching_response.png")))
        """
    ),
    markdown(
        """
        A higher switching rate after closed-unmerged outcomes is consistent with behavioral
        response, but cannot identify who selected the tool or whether agent reputation caused
        the transition. Agent changes frequently coincide with contributor changes.
        """
    ),
    markdown("## RQ3 — When is switching associated with 30-day integration?"),
    code(
        """
        rates = pd.read_csv(TABLES / "rq3_recovery_rates.csv")
        heterogeneity = pd.read_csv(TABLES / "rq3_star_heterogeneity.csv")
        model = pd.read_csv(TABLES / "rq3_within_repo_lpm.csv")
        display(rates[["prior_outcome", "transition_type", "n", "merge_rate"]])
        display(heterogeneity)
        display(model.loc[model["term"].isin([
            "switched", "switched_after_prior_merged"
        ])])
        display(Image(filename=str(FIGURES / "rq3_recovery_crossover.png")))
        display(Image(filename=str(FIGURES / "rq3_switching_heterogeneity.png")))
        display(Image(filename=str(FIGURES / "rq2_adjusted_switching_contrasts.png")))
        """
    ),
    markdown(
        """
        The association is heterogeneous and disappears in the 100+ star stratum. That is a
        useful boundary condition and a warning that long-tail repository composition may
        drive the aggregate result. Repository-demeaned estimates reduce stable between-repo
        differences but remain non-causal.
        """
    ),
    markdown(
        """
        ## Takeaways

        1. Keep the paper to three RQs and make outcome-conditioned switching the spine.
        2. Treat repository maturity as a first-class boundary condition.
        3. Before any causal language, add task/complexity controls from AIDev-pop, agent-pair
           sensitivity, high-volume-repository robustness, and manually validate sampled
           transition episodes.
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
NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(notebook, NOTEBOOK_PATH)
print(NOTEBOOK_PATH)
