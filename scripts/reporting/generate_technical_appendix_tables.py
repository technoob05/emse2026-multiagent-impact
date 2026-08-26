"""Generate every quantitative table used by the technical appendix.

The appendix deliberately keeps its detailed values out of hand-written TeX.
This script reads the validated analysis products, checks their schemas, formats
paper-safe labels, and writes one deterministic TeX fragment.  It fails closed
when an expected input, column, row, or table label is missing.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "paper" / "manuscript" / "generated_appendix_tables.tex"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from multiagent_impact.cross_agent_review import AGENT_ACCOUNT_ALIASES  # noqa: E402


EXPECTED_LABELS = {
    "tab:s-dataset",
    "tab:s-coverage",
    "tab:s-identity",
    "tab:s-funnel",
    "tab:s-burst",
    "tab:s-deep-transition",
    "tab:s-falsification",
    "tab:s-boundary",
    "tab:s-history",
    "tab:s-addressed-edge",
    "tab:s-landmark-route",
    "tab:s-sensitivity",
    "tab:s-exposure-scope",
    "tab:s-extensions",
    "tab:s-task-context",
    "tab:s-collision",
    "tab:s-external-screen",
    "tab:s-external-edge",
    "tab:s-external-attribution",
    "tab:s-quality",
    "tab:s-disposition",
    "tab:s-glossary",
    "tab:s-specifications",
    "tab:s-ties",
    "tab:s-ordering",
    "tab:s-gradient",
    "tab:s-balance",
    "tab:s-variables",
    "tab:s-resampling",
    "tab:s-runorder",
}


def input_path(relative: str) -> Path:
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required input is missing: {relative}")
    return path


def read_csv(relative: str, required: Sequence[str] = ()) -> list[dict[str, str]]:
    path = input_path(relative)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {relative}")
        missing = set(required) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{relative} is missing columns: {sorted(missing)}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError(f"CSV has no data rows: {relative}")
    return rows


def read_json(relative: str) -> dict[str, Any]:
    with input_path(relative).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {relative}")
    return value


def one(rows: Iterable[Mapping[str, str]], **conditions: object) -> Mapping[str, str]:
    matches = [
        row
        for row in rows
        if all(str(row.get(key, "")) == str(value) for key, value in conditions.items())
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one row for {conditions}, found {len(matches)}")
    return matches[0]


def number(value: object) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Expected a finite number, found {value!r}")
    return result


def integer(value: object) -> str:
    return f"{int(round(number(value))):,}"


def percent(value: object, digits: int = 1) -> str:
    return f"{100 * number(value):.{digits}f}"


def pp(value: object, digits: int = 1, signed: bool = True) -> str:
    amount = 100 * number(value)
    return f"{amount:+.{digits}f}" if signed else f"{amount:.{digits}f}"


def ci_percent(low: object, high: object, digits: int = 1) -> str:
    return f"[{percent(low, digits)}, {percent(high, digits)}]"


def ci_pp(low: object, high: object, digits: int = 1) -> str:
    return f"[{pp(low, digits)}, {pp(high, digits)}]"


def compact_number(value: object, digits: int = 1) -> str:
    amount = number(value)
    if abs(amount - round(amount)) < 1e-10:
        return integer(amount)
    return f"{amount:.{digits}f}"


def tex(value: object) -> str:
    mapping = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(mapping.get(character, character) for character in str(value))


def texttt(value: object) -> str:
    return rf"\texttt{{{tex(value)}}}"


def breakable_identifier(value: object) -> str:
    text = str(value)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if any(character not in allowed for character in text):
        raise ValueError(f"Unsafe identifier for nolinkurl: {text!r}")
    return rf"\nolinkurl{{{text}}}"


def row(cells: Sequence[object]) -> str:
    return " & ".join(str(cell) for cell in cells) + r" \\"


def table(
    caption: str,
    label: str,
    columns: str,
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
    note: str,
) -> str:
    body = "\n".join(row(values) for values in rows)
    return f"""\\begin{{table*}}[!htbp]
\\caption{{{tex(caption)}}}\\label{{{label}}}
\\centering
\\small
\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabularx}}{{\\textwidth}}{{@{{}}{columns}@{{}}}}
\\toprule
{row(header)}
\\midrule
{body}
\\bottomrule
\\end{{tabularx}}
\\par\\smallskip
\\footnotesize \\textit{{Note:}} {tex(note)}
\\end{{table*}}
"""


def longtable(
    caption: str,
    label: str,
    columns: str,
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
    note: str,
) -> str:
    heading = row(header)
    body = "\n".join(row(values) for values in rows)
    # Pending floats are flushed first, and the table only starts on a fresh page
    # when too little room is left, so that it never leaves one or two orphaned
    # body rows behind a page break. The continuation caption is unnumbered so no
    # second hyperlink anchor is emitted for the same table.
    return f"""\\FloatBarrier
\\needspace{{8\\baselineskip}}
\\begingroup
\\small
\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{longtable}}{{@{{}}{columns}@{{}}}}
\\caption{{{tex(caption)}}}\\label{{{label}}}\\\\
\\toprule
{heading}
\\midrule
\\endfirsthead
\\caption*{{{tex(caption)} (continued)}}\\\\
\\toprule
{heading}
\\midrule
\\endhead
{body}
\\bottomrule
\\end{{longtable}}
\\noindent\\footnotesize \\textit{{Note:}} {tex(note)}
\\endgroup
"""


def longtable_once(
    caption: str,
    label: str,
    columns: str,
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
    note: str,
) -> str:
    """Render a non-floating table with a compact continuation head if it splits."""
    heading = row(header)
    body = "\n".join(row(values) for values in rows)
    return f"""\\FloatBarrier
\\needspace{{8\\baselineskip}}
\\begingroup
\\small
\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{longtable}}{{@{{}}{columns}@{{}}}}
\\caption{{{tex(caption)}}}\\label{{{label}}}\\\\
\\toprule
{heading}
\\midrule
\\endfirsthead
\\caption*{{{tex(caption)} (continued)}}\\\\
\\toprule
{heading}
\\midrule
\\endhead
{body}
\\bottomrule
\\end{{longtable}}
\\noindent\\footnotesize \\textit{{Note:}} {tex(note)}
\\endgroup
"""


def dataset_table() -> str:
    inventory = read_csv(
        "outputs/tables/dataset_table_inventory.csv",
        ("table", "scope", "grain", "rows", "columns", "role"),
    )
    rows = [
        (
            breakable_identifier(item["table"]),
            tex(item["scope"].replace("AIDev-pop (>100 stars)", "Rich layer")),
            tex(item["grain"]),
            integer(item["rows"]),
            integer(item["columns"]),
            tex(item["role"]),
        )
        for item in inventory
    ]
    return longtable(
        "Dataset tables, units, and analytical roles in the pinned release.",
        "tab:s-dataset",
        r"L{0.22\textwidth}L{0.07\textwidth}L{0.16\textwidth}rrL{0.21\textwidth}",
        ("Table", "Scope", "Unit", "Rows", "Fields", "Role"),
        rows,
        "The rich layer contains repositories with more than 100 stars. Row counts come from Parquet metadata, so large content tables are not expanded in memory.",
    )


def coverage_table() -> str:
    coverage = read_csv(
        "outputs/tables/dataset_join_coverage.csv",
        ("feature_group", "event_rows", "matched_pr_ids", "coverage_pct_of_aidev_pop", "orphan_pr_ids"),
    )
    rows = [
        (
            tex(item["feature_group"]),
            integer(item["event_rows"]),
            integer(item["matched_pr_ids"]),
            f"{number(item['coverage_pct_of_aidev_pop']):.2f}",
            integer(item["orphan_pr_ids"]),
        )
        for item in coverage
    ]
    return table(
        "Coverage of rich event and feature tables across 361,296 AIDev-pop pull requests.",
        "tab:s-coverage",
        r"Yrrrr",
        ("Feature group", "Rows", "Matched PRs", "PR coverage (\\%)", "Orphan PR IDs"),
        rows,
        "Coverage means that a pull request has at least one linked row. Inline comments resolve through their submitted-review identifier before joining to the pull request.",
    )


def identity_table() -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for login, product in AGENT_ACCOUNT_ALIASES.items():
        grouped[product].append(login)
    expected_products = {
        "Claude_Code",
        "Copilot",
        "Cursor",
        "Devin",
        "Google_Jules",
        "OpenAI_Codex",
    }
    if set(grouped) != expected_products:
        raise ValueError(f"Unexpected mapped product registry: {sorted(grouped)}")
    rows: list[tuple[str, str]] = []
    for product in sorted(grouped):
        aliases = sorted(grouped[product])
        rows.append((texttt(product), ", ".join(texttt(alias) for alias in aliases)))
    return table(
        "Exact public-account allowlist used for reviewer-product attribution.",
        "tab:s-identity",
        r"L{0.22\textwidth}Y",
        ("Mapped product", "Exact GitHub login(s), matched case-insensitively"),
        rows,
        "Only exact aliases are mapped. Similar names and unknown bots stay outside the six-product registry.",
    )


def funnel_table() -> str:
    funnel = read_csv(
        "outputs/coordination_topology/participation_funnel.csv",
        ("stage", "prs", "share_of_trigger_cohort"),
    )
    complete = one(funnel, stage="Complete cross-product trigger cohort")
    any_action = one(funnel, stage="Any later visible action")
    exact = one(funnel, stage="Exact reply to the trigger")
    mapped_exact = one(funnel, stage="Mapped different-product exact reply")

    chains_path = input_path("outputs/cross_agent_review/cross_feedback_response_chains.parquet")
    trigger_source = pq.read_table(chains_path, columns=["trigger_source"])["trigger_source"]
    inline_eligible = int(pc.sum(pc.equal(trigger_source, "inline_review_comment")).as_py())
    complete_n = int(number(complete["prs"]))
    if len(trigger_source) != complete_n:
        raise ValueError("Response-chain and funnel denominators do not agree")

    records = [
        ("Complete seven-day trigger cohort", complete_n, "Full cohort", 1.0),
        ("Any later visible action", int(number(any_action["prs"])), "Full cohort", number(any_action["prs"]) / complete_n),
        ("Inline trigger; exact reply is observable", inline_eligible, "Full cohort", inline_eligible / complete_n),
        ("Exact parent reply", int(number(exact["prs"])), "Full cohort", number(exact["prs"]) / complete_n),
        ("Exact parent reply", int(number(exact["prs"])), "Inline-eligible", number(exact["prs"]) / inline_eligible),
        ("Mapped different-product exact reply", int(number(mapped_exact["prs"])), "Full cohort", number(mapped_exact["prs"]) / complete_n),
        ("Mapped different-product exact reply", int(number(mapped_exact["prs"])), "Inline-eligible", number(mapped_exact["prs"]) / inline_eligible),
    ]
    rows = [(tex(stage), f"{count:,}", tex(denominator), percent(share)) for stage, count, denominator, share in records]
    return table(
        "Participation-to-addressed-edge denominator funnel.",
        "tab:s-funnel",
        r"Yr L{0.20\textwidth}r",
        ("Stage", "PRs", "Denominator", "Share (\\%)"),
        rows,
        "An exact parent reply is defined only for an inline trigger. The repeated rows make the full-cohort and eligible denominators explicit.",
    )


STATE_LABELS = {
    "user_account": "User account",
    "mapped_product": "Mapped product",
    "other_bot": "Other bot",
    "branch_movement_untyped": "Branch movement or untyped activity",
    "no_action_within_7d": "No later action within seven days",
    "same_mapped_product": "Same mapped product",
    "different_mapped_product": "Different mapped product",
    "no_later_state": "No later state",
}


def burst_table() -> str:
    data = read_csv(
        "outputs/burst_topology/burst_topology_summary.csv",
        (
            "burst_threshold_minutes",
            "first_post_burst_state",
            "prs",
            "share_all_prs",
            "repository_cluster_ci_low",
            "repository_cluster_ci_high",
            "median_minutes_from_burst_end",
        ),
    )
    rows = []
    for threshold in (0, 1, 5, 10, 30):
        selected = [item for item in data if int(number(item["burst_threshold_minutes"])) == threshold]
        if len(selected) != 5:
            raise ValueError(f"Expected five states at the {threshold}-minute threshold")
        for item in selected:
            median = item["median_minutes_from_burst_end"]
            rows.append(
                (
                    str(threshold),
                    tex(STATE_LABELS[item["first_post_burst_state"]]),
                    integer(item["prs"]),
                    percent(item["share_all_prs"]),
                    ci_percent(item["repository_cluster_ci_low"], item["repository_cluster_ci_high"]),
                    "--" if median == "" else compact_number(median),
                )
            )
    return longtable(
        "First public state after each rapid-burst threshold.",
        "tab:s-burst",
        r"r L{0.21\textwidth}r r L{0.14\textwidth}r",
        ("Burst (min)", "First state", "PRs", "Share (\\%)", "Cluster 95\\% interval", "Median min"),
        rows,
        "The denominator is 8,608 PRs at every threshold. The window is a sensitivity parameter, not an inferred private session boundary.",
    )


def deep_transition_table() -> str:
    transitions = read_csv(
        "outputs/deep_coordination/mapped_first_next_owner_summary.csv",
        ("washout_minutes", "next_owner_state", "prs", "share", "repository_cluster_ci_low", "repository_cluster_ci_high"),
    )
    placebo = read_csv(
        "outputs/deep_coordination/mapped_product_order_placebo_summary.csv",
        (
            "washout_minutes",
            "eligible_prs",
            "observed_same_product_share",
            "random_order_expected_share",
            "observed_minus_random_order",
            "repository_cluster_difference_ci_low",
            "repository_cluster_difference_ci_high",
        ),
    )
    selected = [item for item in transitions if int(number(item["washout_minutes"])) == 5]
    if len(selected) != 6:
        raise ValueError("Expected six deep-transition states after the five-minute washout")
    rows: list[tuple[str, str, str, str]] = []
    for item in selected:
        rows.append(
            (
                tex(f"Next state: {STATE_LABELS[item['next_owner_state']]}"),
                integer(item["prs"]),
                percent(item["share"]),
                ci_percent(item["repository_cluster_ci_low"], item["repository_cluster_ci_high"]),
            )
        )
    p = one(placebo, washout_minutes="5")
    rows.extend(
        [
            (tex("Same-product continuation among later mapped events: observed"), integer(p["eligible_prs"]), percent(p["observed_same_product_share"]), "--"),
            (tex("Same-product continuation: random-order expectation"), integer(p["eligible_prs"]), percent(p["random_order_expected_share"]), "--"),
            (tex("Observed minus random-order expectation (percentage points)"), integer(p["eligible_prs"]), pp(p["observed_minus_random_order"]), ci_pp(p["repository_cluster_difference_ci_low"], p["repository_cluster_difference_ci_high"])),
        ]
    )
    return table(
        "Deep transition after a mapped-product first state and a second five-minute washout.",
        "tab:s-deep-transition",
        r"Yrr L{0.22\textwidth}",
        ("Quantity", "PRs", "Estimate", "Repository-cluster 95\\% interval"),
        rows,
        "The next-state shares use 924 mapped-first PRs. The placebo uses 495 PRs with a later mapped-product event and preserves each PR's future product composition.",
    )


def falsification_table() -> str:
    transitions = read_csv(
        "outputs/deep_coordination/automation_episode_transition_summary.csv",
        ("episode_gap_minutes", "automation_state", "next_transition", "at_risk_prs", "share"),
    )
    permutations = read_csv(
        "outputs/deep_coordination/automation_order_permutation_placebo.csv",
        (
            "episode_gap_minutes",
            "automation_state",
            "next_transition",
            "permuted_order_mean_share",
            "permuted_order_ci_low",
            "permuted_order_ci_high",
        ),
    )
    ownership = read_csv(
        "outputs/ownership_persistence/conditional_visible_action_contrasts.csv",
        (
            "metric",
            "user_first_estimate",
            "mapped_first_estimate",
            "user_minus_mapped",
            "repository_cluster_ci_low",
            "repository_cluster_ci_high",
        ),
    )
    metric_labels = {
        "exact_owner_persistence": "Exact owner repeats",
        "layer_persistence": "Same ownership layer continues",
        "cross_layer_handoff": "Cross-layer handoff (user--product bounce)",
    }
    rows: list[tuple[str, str, str, str, str]] = []
    for state in (1, 2, 3, 4):
        observed = one(
            transitions,
            episode_gap_minutes="5",
            automation_state=str(state),
            next_transition="user_account",
        )
        null = one(
            permutations,
            episode_gap_minutes="5",
            automation_state=str(state),
            next_transition="user_account",
        )
        rows.append(
            (
                tex(f"Automation episode {state}: next is a user"),
                integer(observed["at_risk_prs"]),
                percent(observed["share"]),
                percent(null["permuted_order_mean_share"]),
                ci_percent(null["permuted_order_ci_low"], null["permuted_order_ci_high"]),
            )
        )
    for item in ownership:
        metric = item["metric"]
        if metric not in metric_labels:
            raise ValueError(f"Unknown ownership-persistence metric: {metric}")
        rows.append(
            (
                tex(f"Visible next action: {metric_labels[metric]}"),
                "3,237 start PRs",
                f"user {percent(item['user_first_estimate'])}; product {percent(item['mapped_first_estimate'])}",
                pp(item["user_minus_mapped"]),
                ci_pp(item["repository_cluster_ci_low"], item["repository_cluster_ci_high"]),
            )
        )
    return table(
        "Falsification tests for escalation and persistent ownership stories.",
        "tab:s-falsification",
        r"Y L{0.13\textwidth} L{0.22\textwidth} L{0.15\textwidth} L{0.18\textwidth}",
        ("Test", "At risk", "Observed (\\%)", "Null or difference (pp)", "95\\% interval"),
        rows,
        "Automation rows compare the observed user-next share with a within-PR order permutation. Ownership rows condition on a visible next action; their fourth column is user-first minus mapped-first. Same-layer continuation and cross-layer bounce show no clear group difference, while exact owner repetition is higher after a mapped-product first state.",
    )


def boundary_table() -> str:
    data = read_csv(
        "outputs/coordination_topology/matched_visibility_contrasts.csv",
        (
            "specification",
            "outcome",
            "pairs",
            "repositories",
            "cross_rate",
            "same_rate",
            "paired_difference",
            "repository_cluster_bootstrap_ci_low",
            "repository_cluster_bootstrap_ci_high",
        ),
    )
    outcome_labels = {
        "any_visible_followup": "Any visible follow-up",
        "later_pr_comment": "Later PR comment",
        "new_review_round": "New review round",
        "exact_trigger_reply": "Exact trigger reply",
        "visible_force_push": "Visible force-push",
        "merge_within_7d": "Merge within seven days",
    }
    rows = []
    for outcome in outcome_labels:
        item = one(data, specification="exact_author_user", outcome=outcome)
        rows.append(
            (
                tex(outcome_labels[outcome]),
                integer(item["pairs"]),
                percent(item["cross_rate"]),
                percent(item["same_rate"]),
                pp(item["paired_difference"]),
                ci_pp(item["repository_cluster_bootstrap_ci_low"], item["repository_cluster_bootstrap_ci_high"]),
            )
        )
    sensitivity = one(data, specification="exact_author_user_7d_time_caliper", outcome="any_visible_followup")
    rows.append(
        (
            tex("Any visible follow-up; seven-day pairing caliper"),
            integer(sensitivity["pairs"]),
            percent(sensitivity["cross_rate"]),
            percent(sensitivity["same_rate"]),
            pp(sensitivity["paired_difference"]),
            ci_pp(sensitivity["repository_cluster_bootstrap_ci_low"], sensitivity["repository_cluster_bootstrap_ci_high"]),
        )
    )
    return table(
        "Exact-author matched cross-product versus same-product trigger comparison.",
        "tab:s-boundary",
        r"Yrrrr L{0.18\textwidth}",
        ("Outcome", "Pairs", "Cross (\\%)", "Same (\\%)", "Difference (pp)", "Repository-cluster 95\\% interval"),
        rows,
        "Pairs also match repository, author product, trigger source, and month, then use nearest trigger time without replacement. Difference is cross-product minus same-product.",
    )


def history_table() -> str:
    roles = read_csv(
        "outputs/human_memory_bridge/first_mediator_role_summary.csv",
        ("account_role", "prs", "repositories", "prior_reviewer_share", "median_prior_review_prs_among_experienced"),
    )
    decisive = read_csv(
        "outputs/human_memory_bridge/first_decisive_reviewer_role_summary.csv",
        ("account_role", "prs", "repositories", "prior_reviewer_share", "median_prior_review_prs_among_experienced"),
    )
    baselines = read_csv(
        "outputs/human_memory_bridge/observable_population_baselines.csv",
        ("population", "rows", "repositories", "prior_reviewer_share", "median_prior_review_prs_among_experienced"),
    )
    selected = [
        ("First user bridge: PR author", one(roles, account_role="author_account"), "prs"),
        ("First user bridge: another account", one(roles, account_role="other_user"), "prs"),
        ("All first user bridges", one(roles, account_role="all_first_mediators"), "prs"),
        ("First later decisive reviewer", one(decisive, account_role="all_first_decisive_reviewers"), "prs"),
        ("All distinct 48-hour user responders", one(baselines, population="all_distinct_48h_user_responders"), "rows"),
        ("Cross-feedback PR author accounts", one(baselines, population="all_cross_feedback_pr_author_accounts"), "rows"),
    ]
    rows = [
        (
            tex(label),
            integer(item[count_field]),
            integer(item["repositories"]),
            percent(item["prior_reviewer_share"]),
            "--" if item["median_prior_review_prs_among_experienced"] == "" else compact_number(item["median_prior_review_prs_among_experienced"]),
        )
        for label, item, count_field in selected
    ]
    return table(
        "Strict prior same-repository review history across user-account populations.",
        "tab:s-history",
        r"Y L{0.14\textwidth}L{0.12\textwidth}L{0.15\textwidth}L{0.16\textwidth}",
        ("Population", "Account--PR rows", "Repos", "With prior history (\\%)", "Median prior PRs if experienced"),
        rows,
        "Prior history requires the same account, the same repository, a different PR, and a submitted review strictly before the cross-product trigger. It is observable public history, not verified memory retrieval.",
    )


def addressed_edge_table() -> str:
    models = read_csv(
        "outputs/addressed_edge_landmark/addressed_edge_clustered_lpm.csv",
        ("threshold_hours", "specification", "estimate", "ci_low", "ci_high", "p_value", "n_prs", "repositories"),
    )
    denominators = read_csv(
        "outputs/addressed_edge_landmark/denominators.csv",
        ("threshold_hours", "exposure_group", "prs", "later_merge_rate"),
    )
    fixed = read_csv(
        "outputs/addressed_edge_landmark/repository_fe_sensitivity.csv",
        ("threshold_hours", "specification", "estimate", "ci_low", "ci_high"),
    )
    loo = read_csv(
        "outputs/addressed_edge_landmark/leave_one_product_pair_out_summary.csv",
        ("threshold_hours", "specification", "estimate_min", "estimate_max", "ci_low_min", "ci_low_max"),
    )
    specificity = read_csv(
        "outputs/addressed_edge_specificity/clustered_specificity_lpm.csv",
        (
            "contrast",
            "threshold_hours",
            "repository_fixed_effects",
            "estimate",
            "ci_low",
            "ci_high",
            "n_prs",
            "exposed_prs",
            "control_prs",
            "exposed_raw_merge_rate",
            "control_raw_merge_rate",
        ),
    )
    overlap = read_csv(
        "outputs/addressed_edge_specificity/propensity_overlap_sensitivity.csv",
        ("specification", "contrast", "threshold_hours", "estimate", "ci_low", "ci_high", "n_prs", "exposed_prs", "control_prs"),
    )
    specificity_fe = read_csv(
        "outputs/addressed_edge_specificity/repository_fe_sensitivity.csv",
        (
            "contrast",
            "threshold_hours",
            "repository_fixed_effects",
            "estimate",
            "ci_low",
            "ci_high",
            "n_prs",
            "exposed_prs",
            "control_prs",
            "repositories_with_within_exposure_variation",
        ),
    )
    rows: list[tuple[str, str, str, str, str, str]] = []
    for threshold in (1, 6, 24, 48):
        exposed = one(denominators, threshold_hours=str(threshold), exposure_group="exact_parent_reply_by_threshold")
        unexposed = one(denominators, threshold_hours=str(threshold), exposure_group="no_exact_parent_reply_by_threshold")
        for specification, label in (
            ("A_pretrigger_only", "Pre-trigger adjusted"),
            ("B_route_decomposition", "Route decomposition"),
        ):
            model = one(models, threshold_hours=str(threshold), specification=specification)
            rows.append(
                (
                    f"{threshold} h",
                    tex(label),
                    integer(exposed["prs"]),
                    f"{percent(exposed['later_merge_rate'])} / {percent(unexposed['later_merge_rate'])}",
                    pp(model["estimate"]),
                    ci_pp(model["ci_low"], model["ci_high"]),
                )
            )
    fe = one(fixed, threshold_hours="48", specification="A_pretrigger_only")
    rows.append(("48 h", tex("Repository fixed effects"), "109", "55.0 / 37.9", pp(fe["estimate"]), ci_pp(fe["ci_low"], fe["ci_high"])))
    leave = one(loo, threshold_hours="48", specification="A_pretrigger_only")
    rows.append(
        (
            "48 h",
            tex("Leave one ordered product pair out"),
            tex("at least 70"),
            "--",
            f"{pp(leave['estimate_min'])} to {pp(leave['estimate_max'])}",
            f"lower bounds {pp(leave['ci_low_min'])} to {pp(leave['ci_low_max'])}",
        )
    )
    discussion = one(
        specificity,
        contrast="exact_edge_vs_nonexact_discussion",
        threshold_hours="48",
        repository_fixed_effects="False",
    )
    discussion_overlap = one(
        overlap,
        specification="overlap_weighted_all",
        contrast="exact_edge_vs_nonexact_discussion",
        threshold_hours="48",
    )
    discussion_fe = one(
        specificity_fe,
        contrast="exact_edge_vs_nonexact_discussion",
        threshold_hours="48",
        repository_fixed_effects="True",
    )
    for item in (discussion, discussion_overlap, discussion_fe):
        if int(number(item["n_prs"])) != 615 or int(number(item["exposed_prs"])) != 109 or int(number(item["control_prs"])) != 506:
            raise ValueError("Specificity denominators do not match the frozen 48-hour discussion cohort")
    rows.extend(
        [
            (
                "48 h",
                tex("Specificity: exact edge vs non-exact discussion"),
                "109 of 615",
                f"{percent(discussion['exposed_raw_merge_rate'])} / {percent(discussion['control_raw_merge_rate'])}",
                pp(discussion["estimate"]),
                ci_pp(discussion["ci_low"], discussion["ci_high"]),
            ),
            (
                "48 h",
                tex("Specificity: overlap weighting"),
                "109 of 615",
                "--",
                pp(discussion_overlap["estimate"]),
                ci_pp(discussion_overlap["ci_low"], discussion_overlap["ci_high"]),
            ),
            (
                "48 h",
                tex("Specificity: repository fixed effects"),
                "109 of 615",
                "--",
                pp(discussion_fe["estimate"]),
                f"{ci_pp(discussion_fe['ci_low'], discussion_fe['ci_high'])}; {integer(discussion_fe['repositories_with_within_exposure_variation'])} varying repos",
            ),
        ]
    )
    return table(
        "Exact-parent addressed edge and later merge from the 48-hour landmark through day 30.",
        "tab:s-addressed-edge",
        r"L{0.10\textwidth}Yr L{0.15\textwidth}L{0.13\textwidth}L{0.20\textwidth}",
        ("Reply window", "Specification", "Edge PRs", "Raw merge: edge / no edge (\\%)", "Adjusted difference (pp)", "95\\% interval"),
        rows,
        "The main models use 1,067 inline-trigger PRs in 469 repositories that were open at hour 48 and had a complete 30-day horizon. Specificity rows compare 109 exact-edge PRs with 506 PRs that had public discussion but no exact edge. This post-trigger discussion control is a structural falsification check, not a causal or semantic-resolution estimate.",
    )


def sensitivity_table() -> str:
    evalues = read_csv(
        "outputs/addressed_edge_sensitivity/e_values.csv",
        (
            "threshold_hours",
            "exposed_prs",
            "unexposed_merge_rate",
            "adjusted_risk_difference",
            "ci_low",
            "ci_high",
            "approximate_risk_ratio",
            "e_value_point",
            "e_value_limit",
        ),
    )
    frontier = read_csv(
        "outputs/addressed_edge_sensitivity/unmeasured_confounder_frontier.csv",
        (
            "prevalence_difference",
            "outcome_difference_to_remove_point_estimate",
            "outcome_difference_to_remove_interval",
        ),
    )
    negative = read_csv(
        "outputs/addressed_edge_sensitivity/negative_control_outcomes.csv",
        (
            "threshold_hours",
            "negative_control_outcome",
            "estimate",
            "ci_low",
            "ci_high",
            "n_prs",
            "passes_null_expectation",
        ),
    )
    permutation = read_csv(
        "outputs/addressed_edge_sensitivity/randomisation_inference.csv",
        (
            "threshold_hours",
            "observed_estimate",
            "permutations",
            "permutation_p_value_two_sided",
            "permutation_quantile_025",
            "permutation_quantile_975",
            "repositories_with_within_exposure_variation",
        ),
    )

    control_labels = {
        "pre_trigger_decisive_review": "Negative control: pre-trigger decisive review",
        "pre_trigger_force_push": "Negative control: pre-trigger branch movement",
        "pre_trigger_user_event": "Negative control: pre-trigger user event",
    }
    rows: list[tuple[str, str, str, str, str]] = []

    for threshold in (1, 6, 24, 48):
        item = one(evalues, threshold_hours=str(threshold))
        rows.append(
            (
                tex("Unmeasured confounding"),
                f"{threshold} h",
                pp(item["adjusted_risk_difference"]),
                ci_pp(item["ci_low"], item["ci_high"]),
                tex(
                    f"risk ratio {number(item['approximate_risk_ratio']):.2f}; "
                    f"E-value {number(item['e_value_point']):.2f}, "
                    f"limit {number(item['e_value_limit']):.2f}"
                ),
            )
        )

    for prevalence in ("0.2", "0.4"):
        item = one(frontier, prevalence_difference=prevalence)
        rows.append(
            (
                tex("Tipping point for one binary factor"),
                "48 h",
                "--",
                "--",
                tex(
                    f"a factor {percent(prevalence, 0)} pp more common among edge PRs must itself carry "
                    f"{percent(item['outcome_difference_to_remove_point_estimate'])} pp of later merge to "
                    f"remove the point estimate, and "
                    f"{percent(item['outcome_difference_to_remove_interval'])} pp to remove the interval"
                ),
            )
        )

    for threshold in (1, 6, 24, 48):
        for key, label in control_labels.items():
            item = one(
                negative,
                threshold_hours=str(threshold),
                negative_control_outcome=key,
            )
            passes = str(item["passes_null_expectation"]).strip().lower() == "true"
            rows.append(
                (
                    tex(label),
                    f"{threshold} h",
                    pp(item["estimate"]),
                    ci_pp(item["ci_low"], item["ci_high"]),
                    tex(
                        "interval covers the null"
                        if passes
                        else "interval excludes the null: residual pre-trigger confounding"
                    ),
                )
            )

    for threshold in (1, 6, 24, 48):
        item = one(permutation, threshold_hours=str(threshold))
        rows.append(
            (
                tex("Randomisation inference (unconditional)"),
                f"{threshold} h",
                pp(item["observed_estimate"]),
                ci_pp(
                    item["permutation_quantile_025"],
                    item["permutation_quantile_975"],
                ),
                tex(
                    f"two-sided p = {number(item['permutation_p_value_two_sided']):.3f} over "
                    f"{integer(item['permutations'])} within-repository permutations across "
                    f"{integer(item['repositories_with_within_exposure_variation'])} repositories"
                ),
            )
        )

    return longtable(
        "Sensitivity of the addressed-edge later-merge association to unmeasured structure.",
        "tab:s-sensitivity",
        r"L{0.22\textwidth}L{0.09\textwidth}L{0.09\textwidth}L{0.15\textwidth}L{0.39\textwidth}",
        (
            "Check",
            "Reply window",
            "Estimate (pp)",
            "95\\% interval or reference band",
            "Sensitivity summary",
        ),
        rows,
        "All rows use the 1,067-PR inline-trigger landmark cohort and the pre-trigger adjusted specification. E-values are computed on an approximate risk-ratio scale from the adjusted risk difference and the unexposed later-merge rate; they state the minimum association an unmeasured factor would need with both the exact edge and later merge, beyond the measured controls. Negative-control outcomes were complete before the trigger, so the exposure cannot produce them and a non-null estimate signals residual confounding rather than an effect. The randomisation rows are different from the others in two ways. They are the unconditional test, which permutes across the whole cohort, and their bracketed pair is the 2.5th to 97.5th percentile of the permuted reference distribution, not a confidence interval for the estimate. That reference distribution is not centred on zero because 423 of 469 repositories contain no exposure variation. The centred conditional version, which is the one quoted in the article, is in the exposure-scope table. None of these checks identifies a causal effect.",
    )


def landmark_route_table() -> str:
    speeds = read_csv(
        "outputs/coordination_topology/route_speed_summary.csv",
        ("ownership_route_48h", "prs", "later_merge_rate", "median_first_action_hours"),
    )
    contrasts = read_csv(
        "outputs/coordination_topology/route_direct_contrasts.csv",
        ("reference_route", "compared_route", "specification", "estimate", "ci_low", "ci_high"),
    )
    labels = {
        "automation_no_human": "Automation, no later user event",
        "automation_then_human": "Automation then user",
        "human_first": "User first",
        "movement_only": "Movement only",
        "other_activity": "Other activity",
        "no_observed_action": "No observed action",
    }
    order = ["automation_no_human", "automation_then_human", "human_first", "movement_only", "other_activity", "no_observed_action"]
    rows = []
    for route in order:
        raw = one(speeds, ownership_route_48h=route)
        median = raw["median_first_action_hours"]
        if route == "automation_no_human":
            estimate = "Reference"
            interval = "--"
        else:
            adjusted = one(
                contrasts,
                reference_route="automation_no_human",
                compared_route=route,
                specification="pretrigger_adjusted",
            )
            estimate = pp(adjusted["estimate"])
            interval = ci_pp(adjusted["ci_low"], adjusted["ci_high"])
        rows.append(
            (
                tex(labels[route]),
                integer(raw["prs"]),
                percent(raw["later_merge_rate"]),
                "--" if median == "" else f"{number(median):.2f}",
                estimate,
                interval,
            )
        )
    return table(
        "Forty-eight-hour ownership routes and later integration.",
        "tab:s-landmark-route",
        r"L{0.24\textwidth}L{0.06\textwidth}L{0.10\textwidth}L{0.12\textwidth}L{0.15\textwidth}L{0.20\textwidth}",
        ("Route", "PRs", "Later merge (\\%)", "Median first action (h)", "Adjusted difference (pp)", "Repository-cluster 95\\% interval"),
        rows,
        "The reference is automation with no later user event. Adjustment uses only pre-trigger activity and trigger context. Routes are observed markers, not assigned treatments.",
    )


def plural(value: object, noun: str) -> str:
    count = int(round(number(value)))
    return f"{count:,} {noun}" + ("" if count == 1 else "s")


def exposure_scope_table() -> str:
    composition = read_csv(
        "outputs/addressed_edge_scope/exposure_event_composition.csv",
        ("response_actor_role", "events", "prs", "share_of_exposure_events"),
    )
    definitions = read_csv(
        "outputs/addressed_edge_scope/exposure_definition_models.csv",
        (
            "exposure",
            "definition",
            "exposed_prs",
            "exposed_raw_merge_rate",
            "estimate",
            "ci_low",
            "ci_high",
        ),
    )
    selection = read_csv(
        "outputs/addressed_edge_scope/landmark_selection_funnel.csv",
        ("stage", "prs", "share_of_inline_triggers"),
    )
    conditional = read_csv(
        "outputs/addressed_edge_scope/conditional_randomisation_inference.csv",
        (
            "repositories",
            "n_prs",
            "exposed_prs",
            "observed_estimate",
            "permutations",
            "permutation_mean",
            "permutation_p_value_two_sided",
        ),
    )

    role_labels = {
        "author_account": "PR author's own user account",
        "other_human": "Another user account",
        "triggering_reviewer_brand": "The triggering product itself",
        "other_bot": "An unmapped bot",
        "author_agent_brand": "The PR author's product",
        "other_agent_brand": "A different mapped product",
    }
    rows: list[tuple[str, str, str, str]] = []

    for item in selection:
        rows.append(
            (
                tex("Cohort restriction"),
                tex(item["stage"]),
                integer(item["prs"]),
                f"{percent(item['share_of_inline_triggers'])}\\% of cross-product inline triggers",
            )
        )

    for item in composition:
        label = role_labels.get(
            item["response_actor_role"], str(item["response_actor_role"])
        )
        rows.append(
            (
                tex("Who writes the edge"),
                tex(label),
                plural(item["events"], "event"),
                f"{percent(item['share_of_exposure_events'])}\\% of exposure events on "
                + plural(item["prs"], "PR"),
            )
        )

    for item in definitions:
        estimate = item["estimate"].strip()
        if estimate:
            summary = f"{pp(estimate)} pp {ci_pp(item['ci_low'], item['ci_high'])}"
        else:
            summary = tex("not modelled: too few exposed PRs")
        rows.append(
            (
                tex("Exposure definition"),
                tex(item["definition"]),
                integer(item["exposed_prs"]),
                summary,
            )
        )

    test = conditional[0]
    rows.append(
        (
            tex("Within-repository randomisation"),
            tex("Repositories that can be re-randomised, with repository fixed effects"),
            f"{integer(test['n_prs'])} PRs in {integer(test['repositories'])} repos",
            tex(
                f"observed {pp(test['observed_estimate'])} pp; reference mean "
                f"{pp(test['permutation_mean'])} pp over {integer(test['permutations'])} "
                f"permutations; two-sided p = {number(test['permutation_p_value_two_sided']):.3f}"
            ),
        )
    )

    return longtable(
        "Scope of the addressed-edge exposure and of the landmark cohort.",
        "tab:s-exposure-scope",
        r"L{0.19\textwidth}L{0.30\textwidth}L{0.13\textwidth}L{0.32\textwidth}",
        ("Aspect", "Item", "Size", "Value"),
        rows,
        "The exposure rule requires a reply whose parent identifier is the trigger's own identifier; it does not require another product to write it. The composition rows report who actually wrote the 128 exposure events on the 109 exposed PRs. The exposure-definition rows refit the primary pre-trigger adjusted model on the same 1,067-PR cohort under stricter definitions. The cohort-restriction rows show that the landmark cohort is the slower-resolving remainder of the cross-product inline-trigger population. The randomisation row uses only repositories containing both exposed and unexposed PRs, so its reference distribution is centred; an unconditional permutation of a model without repository fixed effects is not, because the between-repository part of the coefficient is invariant to a within-repository permutation.",
    )


def extensions_table() -> str:
    hazard = read_csv(
        "outputs/rq3_extensions/whole_population_hazard.csv",
        (
            "specification",
            "hazard_odds_ratio",
            "or_ci_low",
            "or_ci_high",
            "p_value",
            "prs",
            "person_period_rows",
            "repositories",
        ),
    )
    classes = read_csv(
        "outputs/rq3_extensions/edge_class_contrasts.csv",
        ("edge_class", "prs", "raw_later_merge_rate", "estimate", "ci_low", "ci_high"),
    )
    robustness = read_csv(
        "outputs/rq3_extensions/history_moderation_robustness.csv",
        ("check", "detail", "estimate", "ci_low", "ci_high"),
    )

    hazard_labels = {
        "A_baseline_hazard_only": "Whole population: time only",
        "B_products_and_month": "Whole population: products and month",
        "C_full_pretrigger": "Whole population: full pre-trigger controls",
    }
    class_labels = {
        "edge_by_known_reviewer": "Edge written by a prior reviewer of this repository",
        "edge_by_newcomer": "Edge written by an account new to this repository",
        "edge_by_automation": "Edge written by automation",
    }

    rows: list[tuple[str, str, str, str]] = []
    for key, label in hazard_labels.items():
        item = one(hazard, specification=key)
        rows.append(
            (
                tex(label),
                f"{integer(item['prs'])} PRs, {integer(item['person_period_rows'])} periods",
                f"{number(item['hazard_odds_ratio']):.2f}",
                tex(
                    f"[{number(item['or_ci_low']):.2f}, {number(item['or_ci_high']):.2f}]; "
                    f"p = {number(item['p_value']):.2g}"
                ),
            )
        )

    for key, label in class_labels.items():
        item = one(classes, edge_class=key)
        rows.append(
            (
                tex(label),
                f"{integer(item['prs'])} PRs, raw {percent(item['raw_later_merge_rate'])}\\%",
                f"{pp(item['estimate'])} pp",
                ci_pp(item["ci_low"], item["ci_high"]),
            )
        )

    for item in robustness:
        rows.append(
            (
                tex(f"Prior reviewer minus newcomer: {item['check'].lower()}"),
                tex(item["detail"]),
                f"{pp(item['estimate'])} pp",
                ci_pp(item["ci_low"], item["ci_high"]),
            )
        )

    return longtable(
        "Extensions to RQ3: the whole population over time, and who writes the edge.",
        "tab:s-extensions",
        r"L{0.34\textwidth}L{0.22\textwidth}L{0.12\textwidth}L{0.28\textwidth}",
        ("Analysis", "Size", "Estimate", "95\\% interval"),
        rows,
        "The whole-population rows drop the hour-48 restriction. Every cross-product inline-trigger PR with a complete 30-day horizon is followed from its trigger, follow-up is split into eleven intervals, and the exact addressed edge enters as a time-varying covariate, so a PR contributes unexposed periods until its own first exact reply. The estimate is an odds ratio for merging in the next interval, from a pooled logistic model with interval indicators and repository-clustered standard errors. The edge-class rows split the 109 exposed PRs of the landmark cohort by the account that wrote the first exact reply, using the same strict prior-history rule as the RQ2 analysis, against the no-edge reference. The final block repeats that split under repository fixed effects and under leave-one-out exclusions. The fixed-effect row is the decisive one: the gap between a prior reviewer and a newcomer is largely a difference between repositories, not within them, so these rows describe where the signal sits and do not identify a mechanism.",
    )


def task_context_table() -> str:
    cells = read_csv(
        "outputs/task_context_interaction/answer_rate_cells.csv",
        (
            "reviewer_relation",
            "body_issue_link",
            "prs",
            "repositories",
            "answered",
            "answered_rate",
            "population",
        ),
    )
    models = read_csv(
        "outputs/task_context_interaction/interaction_models.csv",
        ("specification", "estimate", "ci_low", "ci_high", "n_prs", "repositories"),
    )
    shuffle = read_csv(
        "outputs/task_context_interaction/label_shuffle_test.csv",
        (
            "observed_estimate",
            "draws",
            "null_mean",
            "null_sd",
            "p_value_two_sided",
        ),
    )[0]
    loo = read_csv(
        "outputs/task_context_interaction/leave_one_repository_out.csv",
        ("excluded_exposed_prs", "estimate"),
    )

    relation_label = {
        "cross_product": "Reviewer is a different product",
        "same_product": "Reviewer is the same product",
    }
    rows: list[tuple[str, str, str, str]] = []
    for item in cells:
        if item["population"] != "thread-root triggers":
            continue
        link = str(item["body_issue_link"]).strip().lower() == "true"
        rows.append(
            (
                tex(relation_label[item["reviewer_relation"]]),
                tex("PR body links an issue" if link else "No issue link"),
                f"{integer(item['answered'])} of {integer(item['prs'])}",
                f"{percent(item['answered_rate'])}\\% over {integer(item['repositories'])} repositories",
            )
        )

    for item in models:
        rows.append(
            (
                tex("Difference in differences"),
                tex(item["specification"]),
                f"{pp(item['estimate'])} pp",
                f"{ci_pp(item['ci_low'], item['ci_high'])} on {integer(item['n_prs'])} PRs",
            )
        )

    estimates = [number(item["estimate"]) for item in loo]
    rows.append(
        (
            tex("Difference in differences"),
            tex(f"Leave one repository out, {len(loo)} refits"),
            f"{pp(min(estimates))} to {pp(max(estimates))} pp",
            tex("each drop removes one of the most influential repositories"),
        )
    )
    rows.append(
        (
            tex("Difference in differences"),
            tex("Issue-link label shuffled inside each repository"),
            f"{pp(shuffle['null_mean'])} pp",
            tex(
                f"null spread {pp(shuffle['null_sd'], signed=False)} pp over "
                f"{integer(shuffle['draws'])} draws; observed "
                f"{pp(shuffle['observed_estimate'])} pp, two-sided p = "
                f"{number(shuffle['p_value_two_sided']):.3f}"
            ),
        )
    )

    return longtable(
        "Issue links and whether a review point is answered, by reviewer relation.",
        "tab:s-task-context",
        r"L{0.24\textwidth}L{0.28\textwidth}L{0.14\textwidth}L{0.30\textwidth}",
        ("Group", "Condition", "Answered", "Detail"),
        rows,
        "The exposure is a pre-trigger property of the change: the pull request body references an issue. The outcome is a later inline comment whose reply target is the trigger comment, strictly after it and within 48 hours, rebuilt from the raw comment table so that both reviewer relations are measured the same way. The population is restricted to triggers that open their own thread, because a mid-thread trigger cannot receive such a reply at all; that restriction removes 0.4 per cent of cross-product triggers but 46 per cent of same-product ones, so leaving it in would compare a possible outcome against an impossible one. The unrestricted rows are reported beside the restricted ones. The release carries no timestamp for the issue link and pull request bodies can be edited, so the link is assumed rather than proven to precede the trigger. Nothing here identifies a causal effect.",
    )


def collision_table() -> str:
    audit = read_json("outputs/review_collision/quality_and_sampling_summary.json")
    descriptive = read_json("outputs/novelty_collision_extension/descriptive_summary.json")
    support = descriptive["support"]
    timing = descriptive["timing"]
    exact = descriptive["format_and_exact_text_checks"]
    concentration = descriptive["concentration"]
    gates = audit["falsification_gates"]
    rows = [
        ("Eligible PRs with two or more mapped reviewer products", integer(support["eligible_prs_with_two_or_more_mapped_reviewer_products"]), "Context"),
        ("Canonical same-snapshot, same-locus pairs", integer(support["canonical_loci"]), "Structural population"),
        ("Pull requests with at least one locus", integer(support["pull_requests_with_locus"]), "17.9\\% of eligible PRs"),
        ("Repositories / product pairs", f"{integer(support['repositories'])} / {integer(support['product_pairs'])}", "Support"),
        ("Median gap", f"{number(timing['median_gap_minutes']):.2f} min", "Timing"),
        ("Pairs within five minutes", f"{percent(timing['share_within_5_minutes'])}\\%", f"cluster interval {ci_percent(timing['share_within_5_minutes_repository_cluster_bootstrap_95_interval'][0], timing['share_within_5_minutes_repository_cluster_bootstrap_95_interval'][1])}\\%"),
        ("Open-state pairs within five minutes", f"{percent(timing['open_state_share_within_5_minutes'])}\\%", f"{integer(timing['open_state_loci'])} loci"),
        ("Non-dominant-pair loci within five minutes", f"{percent(timing['non_dominant_product_pair_share_within_5_minutes'])}\\%", f"{integer(timing['non_dominant_product_pair_loci'])} loci"),
        ("Exact normalized comment-body duplicates", integer(exact["exact_normalized_body_duplicate_loci"]), "Not a semantic comparison"),
        ("Largest repository share", f"{percent(concentration['largest_repository_share'])}\\%", tex(gates["largest_repository_supplies_at_most_half"]["status"].upper())),
        ("Largest product-pair share", f"{percent(concentration['largest_product_pair_share'])}\\%", tex(gates["largest_product_pair_supplies_at_most_half"]["status"].upper())),
        ("Blinded packet coverage", integer(audit["support"]["audit_packet_rows_per_coder"]), "Complete population"),
        ("Dual-coder agreement", "Pending", "Need kappa at least 0.70"),
        ("Semantic relation labels", "Pending", "No duplication or complementarity claim"),
    ]
    return table(
        "Structural same-locus review overlap and frozen semantic gates.",
        "tab:s-collision",
        r"Y L{0.22\textwidth} L{0.30\textwidth}",
        ("Quantity or gate", "Observed", "Interpretation or status"),
        rows,
        "Structural co-location and timing do not establish semantic duplication, contradiction, correctness, repair, or coordination. The product-pair generality gate fails because the largest pair exceeds 50 percent.",
    )


def external_screen_table() -> str:
    registry = read_csv(
        "protocol/external_dataset_registry.csv",
        (
            "dataset_id",
            "dataset",
            "unit_grain",
            "exact_public_reply_edges",
            "verdict",
        ),
    )
    selected = (
        (
            "gharchive_rest",
            "YES after REST",
            "Future disjoint time-window replication after REST enrichment; not used in the present estimates",
        ),
        (
            "swe_review_chat",
            "PARTIAL",
            "Full-corpus topology audit; no independent exact-edge cohort survived overlap exclusion",
        ),
        (
            "ai_ai_closed_loop",
            "NO",
            "Product-pair attribution and trigger-time sensitivity on overlapping public PRs",
        ),
        (
            "swe_prbench",
            "NO",
            "Semantic codebook and initiating-feedback audit only; reply topology is not preserved",
        ),
        (
            "swe_review_traj",
            "NO",
            "Controlled generate--review--revise contrast only; not a field replication",
        ),
        (
            "github_agentic_pr",
            "NO",
            "Excluded: adds PRs and diffs but no review-response graph",
        ),
        (
            "trace_commons",
            "NO",
            "Excluded: opt-in private sessions with no stable public PR edge or outcome",
        ),
    )
    rows = []
    for dataset_id, edge, role in selected:
        item = one(registry, dataset_id=dataset_id)
        rows.append(
            (
                tex(item["dataset"]),
                tex(item["unit_grain"]),
                tex(edge),
                tex(role),
            )
        )
    return longtable_once(
        "External evidence ladder after schema, overlap, and construct checks.",
        "tab:s-external-screen",
        r"L{0.22\textwidth}L{0.21\textwidth}L{0.11\textwidth}L{0.38\textwidth}",
        ("Source", "Native unit", "Exact edge", "Role after audit"),
        rows,
        f"The registry contains {len(registry)} screened candidates. Sources are not pooled merely to add rows. A source must preserve the PR, event time, actor, review batch, exact reply parent, and later-state horizon before it can reproduce the declared topology.",
    )


def external_exact_edge_table() -> str:
    funnel = read_csv(
        "protocol/swe_review_chat_exact_edge_funnel_20260826.csv",
        ("order", "stage", "count"),
    )
    pilot = read_json("protocol/swe_review_chat_exact_edge_pilot_20260826.json")
    by_stage = {item["stage"]: item for item in funnel}

    def count(stage: str) -> str:
        if stage not in by_stage:
            raise ValueError(f"Missing SWE-Review-Chat funnel stage: {stage}")
        return integer(by_stage[stage]["count"])

    child_counts = pilot["extraction"]["source_child_relation_to_parent_counts"]
    user_children = int(child_counts.get("user_unmapped_product", 0))
    same_children = int(child_counts.get("same_as_parent_product", 0))
    different_children = int(child_counts.get("different_from_parent_product", 0))
    rows = [
        ("Public PR rows scanned", count("dataset_pr_rows"), "Available corpus"),
        ("PRs whose author maps by the frozen exact alias list", count("exact_alias_mapped_author_prs"), "Product-aware author support"),
        ("PRs with a cross-product inline parent", count("prs_with_any_cross_product_inline_parent"), "Candidate trigger support"),
        ("PRs where such a parent has a nested reply", count("prs_where_qualifying_parent_has_nested_reply"), "Seven candidate PRs before overlap removal"),
        ("Nested children before overlap removal", f"{integer(user_children)} / {integer(same_children)} / {integer(different_children)}", "Unmapped user / same product / different product"),
        ("Candidate PRs outside the AIDev full corpus", count("non_aidev_candidate_prs"), "No independent cohort remains"),
        ("REST-validated 48-hour landmark PRs", count("rest_validated_landmark_eligible_prs"), "Replication gate fails"),
    ]
    return table(
        "Fail-closed exact-edge replication audit in SWE-Review-Chat.",
        "tab:s-external-edge",
        r"Y L{0.16\textwidth} L{0.38\textwidth}",
        ("Stage", "PRs or records", "Meaning"),
        rows,
        "All seven pre-exclusion candidate PRs already occur in the AIDev full corpus. No GitHub comment or PR body was exported. Zero disjoint support is a failed replication gate, not evidence that exact public connections never occur.",
    )


def external_attribution_table() -> str:
    coverage = read_csv(
        "outputs/external_validation/codage_attribution_sensitivity/attribution_coverage.csv",
        ("stage", "prs", "share_of_landmark"),
    )
    temporal = read_csv(
        "outputs/external_validation/codage_attribution_sensitivity/temporal_concordance.csv",
        ("metric", "value"),
    )
    models = read_csv(
        "outputs/external_validation/codage_attribution_sensitivity/later_merge_sensitivity.csv",
        ("specification", "estimate", "ci_low", "ci_high", "n_prs", "repositories", "exposed_prs"),
    )
    overlap = one(coverage, stage="PR also appears in external A2A cross-product cohort")
    agreement = one(coverage, stage="Exact pair agreement conditional on overlapping PR")
    exposed = one(coverage, stage="Exact-edge exposed PRs in exact-pair overlap")
    timestamp_rows = one(temporal, metric="exact-pair rows with both trigger timestamps")
    timestamp_match = one(temporal, metric="absolute timestamp difference within five minutes")
    raw = one(models, specification="unadjusted")
    adjusted = one(models, specification="pretrigger_adjusted")
    rows = [
        ("PR overlap", integer(overlap["prs"]), f"{percent(overlap['share_of_landmark'])}\\% of landmark cohort", "Coverage only"),
        ("Exact author--reviewer pair agrees", integer(agreement["prs"]), f"{percent(agreement['share_of_landmark'])}\\% of overlapping PRs", "Supports product attribution"),
        ("Trigger time agrees within five minutes", integer(timestamp_rows["value"]), f"{percent(timestamp_match['value'])}\\%", "Supports event anchoring"),
        ("Exact-edge exposed PRs", integer(exposed["prs"]), f"{percent(exposed['share_of_landmark'])}\\% of exact-pair overlap", "Too few for replication"),
        ("Raw later-merge difference", integer(raw["n_prs"]), f"{pp(raw['estimate'])} pp", ci_pp(raw["ci_low"], raw["ci_high"])),
        ("Pre-trigger-adjusted difference", integer(adjusted["n_prs"]), f"{pp(adjusted['estimate'])} pp", ci_pp(adjusted["ci_low"], adjusted["ci_high"])),
    ]
    return table(
        "Independent-packaging sensitivity for product attribution and trigger anchoring.",
        "tab:s-external-attribution",
        r"Y L{0.12\textwidth} L{0.25\textwidth} L{0.26\textwidth}",
        ("Check", "PRs", "Observed", "Use"),
        rows,
        "The external cohort was released independently but observes overlapping public GitHub PRs. Its 119-PR exact-pair overlap contains only nine exposed PRs. The merge rows are therefore an appendix sensitivity, not an independent outcome replication or a causal estimate.",
    )


def quality_table() -> str:
    corpus = read_json("outputs/tables/data_quality.json")
    burst = read_csv("outputs/burst_topology/data_quality_checks.csv", ("check", "status", "value", "note"))
    deep = read_csv("outputs/deep_coordination/data_quality_checks.csv", ("check", "status", "value", "note"))
    ownership = read_csv("outputs/ownership_persistence/data_quality_checks.csv", ("check", "status", "value", "note"))
    edge = read_json("outputs/addressed_edge_landmark/temporal_leakage_validation.json")
    history = read_json("outputs/human_memory_bridge/validation.json")
    request = read_json("outputs/review_request_context/validation.json")

    checks = [
        ("Full-corpus PR identifiers are unique", "PASS" if corpus["overview"]["duplicate_ids"] == 0 else "FAIL", integer(corpus["overview"]["unique_ids"])),
        ("Follow-up event PR identifiers resolve", one(burst, check="event_prs_have_chain_parent")["status"], f"{one(burst, check='event_prs_have_chain_parent')['value']} orphan IDs"),
        ("Events are strictly after the trigger", one(burst, check="events_strictly_after_trigger")["status"], f"{one(burst, check='events_strictly_after_trigger')['value']} violations"),
        ("Events stay inside the seven-day window", one(burst, check="events_inside_response_window")["status"], f"{one(burst, check='events_inside_response_window')['value']} violations"),
        ("Later review batches are de-duplicated", one(burst, check="later_reviews_debatched_by_review_id")["status"], f"{one(burst, check='later_reviews_debatched_by_review_id')['value']} repeated batches"),
        ("Exact duplicate event surplus removed", one(ownership, check="exact_duplicate_event_rows_removed")["status"], f"{one(ownership, check='exact_duplicate_event_rows_removed')['value']} rows"),
        ("First state is invariant to exact de-duplication", one(burst, check="first_state_invariant_to_exact_deduplication")["status"], f"{one(burst, check='first_state_invariant_to_exact_deduplication')['value']} changed states"),
        ("Mapped-first anchor reconciles", one(deep, check="mapped_first_anchor_count")["status"], f"{one(deep, check='mapped_first_anchor_count')['value']} PRs"),
        ("Landmark cohort has one row per PR", "PASS" if edge["cohort"]["one_row_per_pr"] else "FAIL", f"{integer(edge['cohort']['unique_prs'])} PRs"),
        ("Direct-reply parent identifiers equal the trigger", "PASS" if edge["exposure"]["all_direct_reply_parent_ids_equal_trigger_event_id"] else "FAIL", f"{integer(edge['exposure']['direct_reply_events_within_48h'])} reply events"),
        ("All positive outcomes occur after hour 48", "PASS" if edge["cohort"]["all_positive_outcomes_after_48h"] else "FAIL", f"{integer(edge['cohort']['outcome_positive_prs'])} outcomes"),
        ("All outcomes stay within the 30-day horizon", "PASS" if edge["cohort"]["all_positive_outcomes_by_30d"] else "FAIL", str(edge["cohort"]["all_positive_outcomes_by_30d"])),
        ("Pre-trigger controls are strictly pre-trigger", "PASS" if edge["pretrigger_controls"]["all_pretrigger_interaction_times_strictly_before_trigger"] else "FAIL", f"{integer(edge['pretrigger_controls']['pretrigger_interaction_rows_used'])} rows"),
        ("Prior-history matches exclude focal and future rows", "PASS" if history["no_same_pr_history_in_valid_matches"] and history["no_future_or_equal_history_in_valid_matches"] else "FAIL", f"{integer(history['responder_history_checks']['valid_prior_history_rows'])} valid rows"),
        ("Review-request target account coverage", "LIMIT", f"{percent(request['assignee_coverage'])}%"),
    ]
    rows = [(tex(name), tex(status), tex(value)) for name, status, value in checks]
    return longtable_once(
        "Load-bearing data-quality, temporal, and leakage checks.",
        "tab:s-quality",
        r"L{0.52\textwidth}L{0.13\textwidth}L{0.28\textwidth}",
        ("Gate", "Status", "Observed"),
        rows,
        "PASS means that the frozen automated check met its declared contract. LIMIT identifies missing measurement coverage rather than a failed computation.",
    )


def disposition_table() -> str:
    data = read_csv(
        "protocol/experiment_disposition_20260826.csv",
        ("experiment_or_claim", "status", "reason"),
    )
    allowed = {"MAIN", "SECONDARY", "APPENDIX", "REJECT", "PENDING"}
    unknown = {item["status"] for item in data} - allowed
    if unknown:
        raise ValueError(f"Unknown experiment disposition(s): {sorted(unknown)}")
    rows = [(tex(item["experiment_or_claim"]), tex(item["status"]), tex(item["reason"])) for item in data]
    return longtable(
        "Experiment and claim disposition after robustness and construct checks.",
        "tab:s-disposition",
        r"L{0.28\textwidth}L{0.16\textwidth}L{0.48\textwidth}",
        ("Experiment or claim", "Status", "Reason"),
        rows,
        "MAIN enters the article's core story; SECONDARY supports that story; APPENDIX is informative but not a headline; REJECT is retained as a falsification result; PENDING requires evidence not yet available.",
    )


def script_source(name: str) -> str:
    """Read a pipeline script by file name, wherever it sits under scripts/."""
    matches = sorted(
        path
        for path in (ROOT / "scripts").rglob(name)
        if "_superseded" not in path.parts
    )
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one active script named {name}, found {len(matches)}"
        )
    return matches[0].read_text(encoding="utf-8")


def require_tokens(text: str, source: str, tokens: Sequence[str]) -> None:
    for token in tokens:
        if token not in text:
            raise ValueError(f"{source} no longer contains {token!r}")


def breakable_code(value: object) -> str:
    """Render code in a fixed-width column that may break wherever it must."""
    pieces: list[str] = []
    for character in str(value):
        pieces.append(tex(character))
        if character != " ":
            pieces.append(r"\allowbreak{}")
    return rf"\texttt{{{''.join(pieces)}}}"


BALANCE_VARIABLE_LABELS = {
    "log1p_trigger_age_hours": "Log trigger age in hours since PR creation",
    "log1p_pre_events": "Log pre-trigger interaction events",
    "pre_user_events": "Pre-trigger user-account events",
    "pre_bot_events": "Pre-trigger bot events",
    "pre_decisive_reviews": "Pre-trigger decisive reviews",
    "pre_force_pushes": "Pre-trigger branch movements",
}


def balance_table() -> str:
    balance = read_csv(
        "outputs/addressed_edge_landmark/pretrigger_balance.csv",
        ("threshold_hours", "variable", "exposed_mean", "unexposed_mean", "standardized_mean_difference"),
    )
    scores = read_csv(
        "outputs/addressed_edge_specificity/propensity_score_diagnostics.csv",
        ("group", "quantile", "propensity_score"),
    )
    rows: list[tuple[str, str, str, str, str]] = []
    for threshold in (1, 6, 24, 48):
        for variable, label in BALANCE_VARIABLE_LABELS.items():
            item = one(balance, threshold_hours=str(threshold), variable=variable)
            rows.append(
                (
                    f"{threshold} h",
                    tex(label),
                    f"{number(item['exposed_mean']):.3f}",
                    f"{number(item['unexposed_mean']):.3f}",
                    f"{number(item['standardized_mean_difference']):+.3f}",
                )
            )
    for quantile in ("0.0", "0.05", "0.25", "0.5", "0.75", "0.95", "1.0"):
        edge = one(scores, group="exact_edge", quantile=quantile)
        control = one(scores, group="nonexact_discussion_only", quantile=quantile)
        rows.append(
            (
                "48 h",
                tex(f"Propensity score at the {percent(quantile, 0)} percentile"),
                f"{number(edge['propensity_score']):.3f}",
                f"{number(control['propensity_score']):.3f}",
                "--",
            )
        )
    return longtable(
        "Pre-trigger covariate balance and propensity overlap for the exact-edge contrast.",
        "tab:s-balance",
        r"L{0.08\textwidth}L{0.32\textwidth}L{0.11\textwidth}L{0.12\textwidth}L{0.16\textwidth}",
        ("Reply window", "Quantity", "Edge mean", "No-edge mean", "Standardized difference"),
        rows,
        "The first block reports the six measured pre-trigger controls in the 1,067-PR landmark cohort. A standardized mean difference is the group difference divided by the pooled standard deviation. Every value is below 0.16 in absolute size. The last block reports the propensity-score distribution of the 109 exact-edge PRs and the 506 non-exact-discussion PRs, so a reader can see where the two groups overlap and where they do not. Balance on measured variables says nothing about unmeasured structure such as task difficulty.",
    )


ROUTE_BASE_FORMULA = (
    "merged_from_48h_to_30d ~ C(ownership_route_48h, Treatment('automation_no_human'))"
    " + C(author_agent) + C(trigger_reviewer_agent) + C(trigger_source) + C(trigger_month)"
)
ROUTE_PRETRIGGER_CONTROLS = (
    "log1p_trigger_age_hours + log1p_pre_events + pre_user_events + pre_bot_events"
    " + pre_decisive_reviews + pre_force_pushes"
)
ROUTE_ADJUSTED_FORMULA = f"{ROUTE_BASE_FORMULA} + {ROUTE_PRETRIGGER_CONTROLS}"
HISTORY_MEDIATOR_FORMULA = "prior_different_pr_reviewer ~ other_user"
HISTORY_RESPONDER_FORMULA = "prior_different_pr_reviewer ~ is_first + is_author"

CLUSTERED_ERRORS = "Linear probability model by OLS; cluster-robust by repository"
CLUSTERED_CORRECTED_ERRORS = (
    "Linear probability model by OLS; cluster-robust by repository, finite-sample corrected"
)


def specifications_table() -> str:
    landmark = read_csv(
        "outputs/addressed_edge_landmark/addressed_edge_clustered_lpm.csv",
        ("threshold_hours", "specification", "term", "n_prs", "repositories", "design_columns", "design_rank", "formula"),
    )
    specificity = read_csv(
        "outputs/addressed_edge_specificity/clustered_specificity_lpm.csv",
        ("contrast", "threshold_hours", "exposure", "n_prs", "repositories", "design_columns", "design_rank", "formula"),
    )
    gradient = read_csv(
        "outputs/addressed_edge_specificity/four_state_response_gradient.csv",
        ("contrast", "threshold_hours", "n_prs", "repositories", "formula"),
    )
    routes = read_csv(
        "outputs/coordination_topology/route_direct_contrasts.csv",
        ("reference_route", "compared_route", "specification", "n_prs", "repositories"),
    )
    history = read_csv(
        "outputs/human_memory_bridge/repo_clustered_history_models.csv",
        ("model", "term", "n", "repositories"),
    )
    require_tokens(
        script_source("run_coordination_topology_analysis.py"),
        "the topology script",
        (
            "C(ownership_route_48h, Treatment('automation_no_human'))",
            "C(trigger_source) + C(trigger_month)",
            "\"log1p_trigger_age_hours\"",
            "cov_type=\"cluster\"",
        ),
    )
    require_tokens(
        script_source("run_human_memory_bridge_analysis.py"),
        "the prior-history script",
        ("prior_different_pr_reviewer", "other_user", "is_first", "is_author", "use_correction"),
    )

    def model_row(label: str, exposure: str, item: Mapping[str, str]) -> tuple[str, ...]:
        return (
            tex(label),
            breakable_code("merged_from_48h_to_30d"),
            breakable_code(exposure),
            tex(CLUSTERED_ERRORS),
            f"{integer(item['n_prs'])} / {integer(item['repositories'])}",
            breakable_code(item["formula"]),
        )

    rows: list[tuple[str, ...]] = []
    for specification, label in (
        ("A_pretrigger_only", "Exact edge, pre-trigger adjusted (primary)"),
        ("B_route_decomposition", "Exact edge, route decomposition (secondary)"),
    ):
        item = one(landmark, threshold_hours="48", specification=specification)
        rows.append(model_row(label, item["term"], item))
    for contrast, label in (
        ("exact_edge_vs_nonexact_discussion", "Specificity: edge vs non-exact discussion"),
        ("exact_edge_vs_any_other_visible_activity", "Specificity: edge vs any other visible activity"),
        ("exact_user_edge_vs_nonexact_user_discussion", "Specificity: user edge vs non-exact user discussion"),
    ):
        item = one(
            specificity,
            contrast=contrast,
            threshold_hours="48",
            repository_fixed_effects="False",
        )
        rows.append(model_row(label, item["exposure"], item))
    four_state = one(gradient, contrast="exact_edge_vs_no_visible_activity", threshold_hours="48")
    rows.append(model_row("Four-state response gradient", "specificity_group_48h", four_state))
    for specification, label, formula in (
        ("base_controls", "Ownership route, base controls", ROUTE_BASE_FORMULA),
        ("pretrigger_adjusted", "Ownership route, pre-trigger adjusted", ROUTE_ADJUSTED_FORMULA),
    ):
        item = one(
            routes,
            reference_route="automation_no_human",
            compared_route="human_first",
            specification=specification,
        )
        rows.append(
            (
                tex(label),
                breakable_code("merged_from_48h_to_30d"),
                breakable_code("ownership_route_48h"),
                tex(CLUSTERED_ERRORS),
                f"{integer(item['n_prs'])} / {integer(item['repositories'])}",
                breakable_code(formula),
            )
        )
    for model, label, term, formula in (
        ("first_mediator_other_vs_author", "Prior history: first user bridge", "other_user", HISTORY_MEDIATOR_FORMULA),
        ("all_responders_first_position", "Prior history: all 48-hour responders", "is_first", HISTORY_RESPONDER_FORMULA),
    ):
        item = one(history, model=model, term=term)
        rows.append(
            (
                tex(label),
                breakable_code("prior_different_pr_reviewer"),
                breakable_code(term),
                tex(CLUSTERED_CORRECTED_ERRORS),
                f"{integer(item['n'])} / {integer(item['repositories'])}",
                breakable_code(formula),
            )
        )
    return longtable(
        "Named estimation specifications behind the reported outcome models.",
        "tab:s-specifications",
        r"L{0.15\textwidth}L{0.11\textwidth}L{0.12\textwidth}L{0.14\textwidth}L{0.08\textwidth}L{0.31\textwidth}",
        ("Specification", "Outcome", "Exposure term", "Estimator and errors", "PRs / repos", "Formula"),
        rows,
        "Every row is a linear probability model fitted by ordinary least squares, with standard errors clustered on the repository. Formulas are stored with the analysis products themselves, except the two route rows and the two prior-history rows, whose formulas are read back from the analysis code. The reply-window variants at 1, 6, and 24 hours refit the same formula with the exposure term for that window. A specification describes the fit; it does not claim that the fit identifies an effect.",
    )


def resampling_table() -> str:
    require_tokens(
        script_source("run_coordination_topology_analysis.py"),
        "the topology script",
        ("SEED = 20260826", "draws: int = 10_000"),
    )
    require_tokens(
        script_source("run_burst_collapsed_topology.py"),
        "the burst script",
        ("SEED = 20260826", "default=5_000", "SEED + threshold_minutes", "SEED + 1_000 + threshold"),
    )
    require_tokens(
        script_source("run_deep_coordination_transitions.py"),
        "the deep-transition script",
        ("SEED = 20260826", "default=5_000", "default=500", "SEED + 400", "SEED + 300 + gap * 10 + state"),
    )
    require_tokens(
        script_source("run_legacy_extension_ownership_persistence.py"),
        "the ownership-persistence script",
        ("SEED = 20260826", "default=5_000"),
    )
    require_tokens(
        script_source("run_collision_descriptive_extension.py"),
        "the collision script",
        ("SEED = 20260826", "BOOTSTRAP_REPS = 10_000"),
    )
    require_tokens(
        script_source("run_addressed_edge_confounding_sensitivity.py"),
        "the confounding script",
        ("PERMUTATIONS = 2000", "PERMUTATION_SEED = 20260826"),
    )
    require_tokens(
        script_source("run_addressed_edge_scope_audit.py"),
        "the scope-audit script",
        ("permutations: int = 2000", "default_rng(20260826)"),
    )

    records = (
        ("Matched cross/same visibility contrast", "Whole repositories", "10,000", "20260826", "Percentile band on the pair-weighted difference"),
        ("Matched contrast, pair-level check", "Matched pairs", "10,000", "20260826", "Percentile band"),
        ("Burst first-state shares", "Whole repositories", "5,000", "20260826 plus the threshold in minutes", "Percentile band on each state share"),
        ("Burst mapped-product retention", "Whole repositories", "5,000", "20260826 plus 1,000 plus the threshold", "Percentile band on the difference"),
        ("Deep next-owner shares", "Whole repositories", "5,000", "20260826 plus 100 plus the washout", "Percentile band"),
        ("Same-product continuation placebo", "Whole repositories", "5,000", "20260826 plus 200 plus the washout", "Percentile band on the difference"),
        ("Within-PR product-order placebo", "Event order inside one PR", "500 permutations", "20260826 plus 400", "Permutation mean and percentile band"),
        ("Automation-episode order placebo", "Event order inside one PR", "500 permutations", "20260826 plus 300 plus the gap and state index", "Permutation mean and percentile band"),
        ("Ownership persistence contrasts", "Whole repositories", "5,000", "20260826 plus a fixed metric offset", "Percentile band"),
        ("Same-locus timing share", "Whole repositories", "10,000", "20260826", "Percentile band"),
        ("Randomisation inference, unconditional", "Exposure labels inside each repository", "2,000 permutations", "20260826", "Two-sided permutation p and percentile band"),
        ("Randomisation inference, conditional", "Exposure labels inside each varying repository", "2,000 permutations", "20260826", "Two-sided permutation p against a centred reference"),
        ("All outcome regressions", "None", "--", "--", "Cluster-robust normal approximation, not resampling"),
    )
    rows = [(tex(a), tex(b), tex(c), tex(d), tex(e)) for a, b, c, d, e in records]
    return longtable(
        "Resampling and permutation settings by analysis.",
        "tab:s-resampling",
        r"L{0.21\textwidth}L{0.16\textwidth}L{0.14\textwidth}L{0.18\textwidth}L{0.24\textwidth}",
        ("Analysis", "Resampling unit", "Draws", "Seed", "Interval method"),
        rows,
        "Draw counts are not uniform across the analyses, so they are listed rather than summarized. Every seed is fixed, and offsets are added so that separate quantities inside one script do not reuse one draw sequence. A percentile band is the 2.5th and 97.5th percentile of the draw distribution. The last row records that the regression intervals come from a clustered normal approximation, which is why the exact-edge estimate is also checked by permutation.",
    )


AVAILABILITY_LABELS = {
    "at_or_before_trigger": "At or before the trigger",
    "posttrigger_by_48h": "After the trigger, by hour 48",
    "outcome": "Outcome window, after hour 48",
}


def definition_text(value: object) -> str:
    """Render a machine-written definition string as readable LaTeX.

    Definitions are copied from the analysis schemas, which are written for
    machines. They carry ASCII arrows and unconditioned plurals that must not
    reach the page as they are.
    """
    text = str(value)
    text = re.sub(r"\b1 (minute|hour|day)s\b", r"1 \1", text)
    escaped = tex(text)
    escaped = escaped.replace("-{}", "")
    escaped = escaped.replace("->", r"$\rightarrow$")
    return escaped


def variables_table() -> str:
    schema = read_json("outputs/addressed_edge_landmark/schema.json")
    columns = schema.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("The landmark schema has no column list")
    rows: list[tuple[str, str, str, str]] = []
    for entry in columns:
        availability = entry["available_when"]
        if availability not in AVAILABILITY_LABELS:
            raise ValueError(f"Unknown leakage tag: {availability}")
        dtype = str(entry["dtype"])
        rows.append(
            (
                breakable_identifier(entry["column"]),
                tex("Datetime (UTC)" if dtype.startswith("Datetime") else dtype),
                tex(AVAILABILITY_LABELS[availability]),
                definition_text(entry["definition"]),
            )
        )
    return longtable(
        f"Variable dictionary for the {len(columns)}-column landmark cohort.",
        "tab:s-variables",
        r"L{0.20\textwidth}L{0.10\textwidth}L{0.17\textwidth}L{0.44\textwidth}",
        ("Column", "Type", "Available when", "Definition"),
        rows,
        "The availability column is the leakage tag stored with the cohort itself. Only columns available at or before the trigger enter the primary model. Columns available after the trigger enter the secondary route decomposition and the exposure definition. Columns tagged as outcome are read only after hour 48. Datetime columns are microsecond UTC timestamps.",
    )


REPRODUCTION_STEPS: dict[str, tuple[str, str]] = {
    "uv sync": ("Resolves and installs the pinned dependency graph", ""),
    "run_cross_agent_review_exploration.py": ("Cross-product trigger cohort and seven-day response chains", ""),
    "run_response_ownership_analysis.py": ("First response owner and 48-hour ownership routes", "outputs/response_ownership/ownership_route_48h_summary.csv"),
    "run_response_ownership_robustness.py": ("Leave-one-out ranges for the ownership descriptives", "outputs/response_ownership/ownership_descriptive_leave_one_out_summary.csv"),
    "run_coordination_topology_analysis.py": ("Participation funnel, exact-author matched contrasts, route contrasts", "outputs/coordination_topology/route_direct_contrasts.csv"),
    "run_burst_collapsed_topology.py": ("Burst-threshold first states, tie diagnostics, ordering robustness", "outputs/burst_topology/burst_topology_summary.csv"),
    "run_deep_coordination_transitions.py": ("Post-burst next owners, episode sessionization, order placebos", "outputs/deep_coordination/mapped_first_next_owner_summary.csv"),
    "run_legacy_extension_ownership_persistence.py": ("Exact-owner and layer persistence falsification", "outputs/ownership_persistence/conditional_visible_action_contrasts.csv"),
    "run_human_memory_bridge_analysis.py": ("Strict prior same-repository review history", "outputs/human_memory_bridge/first_mediator_role_summary.csv"),
    "run_addressed_edge_landmark_analysis.py": ("Landmark cohort, schema, balance, primary exact-edge models", "outputs/addressed_edge_landmark/addressed_edge_clustered_lpm.csv"),
    "run_addressed_edge_specificity_analysis.py": ("Discussion controls, overlap weighting, four-state gradient", "outputs/addressed_edge_specificity/clustered_specificity_lpm.csv"),
    "run_addressed_edge_confounding_sensitivity.py": ("E-values, tipping grid, negative controls, permutation test", "outputs/addressed_edge_sensitivity/e_values.csv"),
    "run_addressed_edge_scope_audit.py": ("Exposure composition, stricter definitions, conditional permutation", "outputs/addressed_edge_scope/exposure_event_composition.csv"),
    "run_task_context_interaction.py": ("RQ4 issue-link interaction across the product boundary", "outputs/task_context_interaction/answer_rate_cells.csv"),
    "run_rq3_extensions.py": ("Whole-population time-varying hazard, and the edge split by who wrote it", "outputs/rq3_extensions/edge_class_contrasts.csv"),
    "prepare_review_collision_audit.py": ("Blinded structural same-locus coder packets", "outputs/review_collision/product_pair_concentration.csv"),
    "run_collision_descriptive_extension.py": ("Descriptive timing and concentration for the same-locus population", "outputs/novelty_collision_extension/timing_distribution.csv"),
    "generate_technical_appendix_tables.py": ("Every table in this appendix", ""),
    "validate_response_ownership_outputs.py": ("Re-checks the ownership products against their frozen contracts", ""),
    "validate_coordination_extension_outputs.py": ("Re-checks the topology and landmark products", ""),
    "visualize_manuscript_figures.py": ("The five article figures and the two appendix figures", ""),
    "uv run --with pytest python -m pytest -q": ("Automated test suite", ""),
}


def reproduction_commands() -> list[str]:
    text = input_path("README.md").read_text(encoding="utf-8")
    marker = "## Reproduce the headline analysis"
    if marker not in text:
        raise ValueError("The README no longer documents the headline reproduction order")
    blocks = text.split(marker, 1)[1].split("```")
    if len(blocks) < 2:
        raise ValueError("The README reproduction section has no fenced command block")
    commands = [
        line.strip()
        for line in blocks[1].splitlines()
        if line.strip() and line.strip() != "powershell"
    ]
    if not commands:
        raise ValueError("The README reproduction block is empty")
    return commands


def runorder_table() -> str:
    rows: list[tuple[str, str, str, str]] = []
    for index, command in enumerate(reproduction_commands(), start=1):
        key = command
        if ".py" in command and "pytest" not in command:
            token = next(part for part in command.split() if part.endswith(".py"))
            key = token.replace("\\", "/").rsplit("/", 1)[-1]
        if key not in REPRODUCTION_STEPS:
            raise ValueError(f"Reproduction step is undocumented: {command}")
        produces, artifact = REPRODUCTION_STEPS[key]
        expected = plural(len(read_csv(artifact)), "row") if artifact else "--"
        rows.append((str(index), breakable_code(key), tex(produces), tex(expected)))
    return longtable(
        "Ordered reproduction contract with frozen row counts.",
        "tab:s-runorder",
        r"L{0.05\textwidth}L{0.31\textwidth}L{0.37\textwidth}L{0.13\textwidth}",
        ("Step", "Command", "Produces", "Expected rows"),
        rows,
        "The order is read from the repository README, so this table cannot drift from the documented sequence. The expected-row column names one frozen product per step where a stable count exists; a dash means the step writes figures, validation logs, or binary tables instead. A rerun that changes a listed count is a signal to compare inputs, not to accept the new number.",
    )


def ties_table() -> str:
    require_tokens(
        script_source("run_burst_collapsed_topology.py"),
        "the burst script",
        (
            "ACTION_STATES = STATE_ORDER[:-1]",
            "STATE_PRIORITY = {state: index + 1 for index, state in enumerate(ACTION_STATES)}",
            '"user_account",',
            '"mapped_product",',
            '"other_bot",',
            '"branch_movement_untyped",',
        ),
    )
    diagnostics = read_csv(
        "outputs/burst_topology/tie_diagnostics.csv",
        (
            "burst_threshold_minutes",
            "post_burst_action_prs",
            "first_timestamp_tie_prs",
            "mixed_state_tie_prs",
            "maximum_events_at_first_timestamp",
        ),
    )
    rows = []
    for threshold in (0, 1, 5, 10, 30):
        item = one(diagnostics, burst_threshold_minutes=str(threshold))
        rows.append(
            (
                tex(f"{threshold} minutes"),
                integer(item["post_burst_action_prs"]),
                integer(item["first_timestamp_tie_prs"]),
                integer(item["mixed_state_tie_prs"]),
                integer(item["maximum_events_at_first_timestamp"]),
            )
        )
    return table(
        "Tied first timestamps under the fixed state priority order.",
        "tab:s-ties",
        r"Y L{0.16\textwidth}L{0.15\textwidth}L{0.13\textwidth}L{0.13\textwidth}",
        ("Burst threshold", "PRs with a post-burst action", "Tied first timestamp", "Mixed-state ties", "Largest tie group"),
        rows,
        "The priority order is user account, then mapped product, then other bot, then branch movement or untyped activity. Ties are common because many events share a whole-second timestamp, but a tie changes the assigned state only when the tied events fall in different states. Exactly one mixed-state tie occurs, at the zero-minute threshold, and none occurs at any positive threshold. The order favours the user-account state, which is the state the RQ1 ordering claim rests on, so the diagnostic is reported rather than assumed harmless.",
    )


def ordering_table() -> str:
    robustness = read_csv(
        "outputs/burst_topology/ordering_robustness.csv",
        (
            "burst_threshold_minutes",
            "exclusion_unit",
            "exclusions",
            "minimum_user_minus_mapped_percentage_points",
            "maximum_user_minus_mapped_percentage_points",
            "user_exceeds_mapped_in_every_exclusion",
            "no_action_is_largest_in_every_exclusion",
        ),
    )
    ranges = read_csv(
        "outputs/burst_topology/leave_one_out_ranges.csv",
        (
            "burst_threshold_minutes",
            "exclusion_unit",
            "first_post_burst_state",
            "full_share",
            "minimum_loo_share",
            "maximum_loo_share",
            "maximum_absolute_shift_percentage_points",
            "exclusions",
        ),
    )
    unit_labels = {"repository": "Repository", "product_pair": "Ordered product pair"}
    rows: list[tuple[str, ...]] = []
    for unit in ("repository", "product_pair"):
        for threshold in (0, 1, 5, 10, 30):
            item = one(robustness, burst_threshold_minutes=str(threshold), exclusion_unit=unit)
            gates_hold = (
                str(item["user_exceeds_mapped_in_every_exclusion"]).strip().lower() == "true"
                and str(item["no_action_is_largest_in_every_exclusion"]).strip().lower() == "true"
            )
            rows.append(
                (
                    str(threshold),
                    tex(unit_labels[unit]),
                    tex("User minus mapped product"),
                    "--",
                    f"{number(item['minimum_user_minus_mapped_percentage_points']):.1f} to {number(item['maximum_user_minus_mapped_percentage_points']):.1f} pp",
                    tex(
                        f"both gates hold in all {int(number(item['exclusions'])):,} exclusions"
                        if gates_hold
                        else "a gate fails"
                    ),
                )
            )
    for unit in ("repository", "product_pair"):
        for state in (
            "user_account",
            "mapped_product",
            "other_bot",
            "branch_movement_untyped",
            "no_action_within_7d",
        ):
            item = one(
                ranges,
                burst_threshold_minutes="5",
                exclusion_unit=unit,
                first_post_burst_state=state,
            )
            rows.append(
                (
                    "5",
                    tex(unit_labels[unit]),
                    tex(STATE_LABELS[state]),
                    percent(item["full_share"]),
                    f"{percent(item['minimum_loo_share'])} to {percent(item['maximum_loo_share'])}",
                    tex(f"largest shift {number(item['maximum_absolute_shift_percentage_points']):.2f} pp"),
                )
            )
    return longtable(
        "Leave-one-out ordering robustness for the first post-burst state.",
        "tab:s-ordering",
        r"L{0.07\textwidth}L{0.13\textwidth}L{0.21\textwidth}L{0.08\textwidth}L{0.16\textwidth}L{0.26\textwidth}",
        ("Burst (min)", "Exclusion unit", "Quantity", "Full (\\%)", "Leave-one-out range", "Gate or largest shift"),
        rows,
        "The first block drops one repository, or one ordered author--reviewer product pair, at a time and refits the ordering. Two gates are checked in every exclusion: the user-account share stays above the mapped-product share, and no later action within seven days stays the largest state. The second block reports the share range for each state at the primary five-minute threshold. These checks show that the ordering is not carried by one repository or one product pair. They do not remove selection into the cohort.",
    )


def gradient_table() -> str:
    gradient = read_csv(
        "outputs/addressed_edge_specificity/four_state_response_gradient.csv",
        ("contrast", "threshold_hours", "estimate", "ci_low", "ci_high", "n_prs", "repositories"),
    )
    denominators = read_csv(
        "outputs/addressed_edge_specificity/denominators.csv",
        ("threshold_hours", "population", "group", "prs", "later_merge_rate"),
    )

    def group_cell(group: str) -> str:
        item = one(
            denominators,
            threshold_hours="48",
            population="full_landmark_cohort",
            group=group,
        )
        return f"{integer(item['prs'])} PRs; {percent(item['later_merge_rate'])}\\%"

    records = (
        ("exact_edge_vs_no_visible_activity", "Exact edge vs no visible activity", "exact_edge", "no_visible_activity"),
        ("nonexact_discussion_vs_no_visible_activity", "Non-exact discussion vs no visible activity", "nonexact_discussion_only", "no_visible_activity"),
        ("movement_only_vs_no_visible_activity", "Movement only vs no visible activity", "movement_only", "no_visible_activity"),
        ("exact_edge_vs_nonexact_discussion", "Exact edge vs non-exact discussion", "exact_edge", "nonexact_discussion_only"),
    )
    rows = []
    for contrast, label, compared, reference in records:
        item = one(gradient, contrast=contrast, threshold_hours="48")
        rows.append(
            (
                tex(label),
                group_cell(compared),
                group_cell(reference),
                pp(item["estimate"]),
                ci_pp(item["ci_low"], item["ci_high"]),
            )
        )
    return table(
        "Four-state contextual response gradient at the 48-hour landmark.",
        "tab:s-gradient",
        r"Y L{0.16\textwidth}L{0.16\textwidth}L{0.11\textwidth}L{0.16\textwidth}",
        ("Contrast", "Compared group", "Reference group", "Difference (pp)", "95\\% interval"),
        rows,
        "One model over the full 1,067-PR landmark cohort in 469 repositories places all four post-trigger states against the no-visible-activity reference, using the same pre-trigger controls as the primary model. The four states are mutually exclusive, so the groups sum to the cohort. The movement-only group holds 26 PRs, so its interval is wide and its point estimate is not a ranking. The active-discussion subset remains the primary specificity contrast because it does not compare an active PR with a silent one.",
    )


def glossary_table() -> str:
    review_module = input_path("src/multiagent_impact/cross_agent_review.py").read_text(encoding="utf-8")
    require_tokens(
        script_source("run_addressed_edge_landmark_analysis.py"),
        "the landmark script",
        ('["APPROVED", "CHANGES_REQUESTED"]', "pre_decisive_reviews"),
    )
    require_tokens(
        review_module,
        "the review module",
        (
            'pl.col("event") == "head_ref_force_pushed"',
            *(
                f'pl.lit("{role}")'
                for role in (
                    "author_account",
                    "author_agent_brand",
                    "triggering_reviewer_brand",
                    "other_agent_brand",
                    "other_bot",
                    "other_human",
                    "unknown_actor",
                )
            ),
        ),
    )
    require_tokens(
        script_source("run_burst_collapsed_topology.py"),
        "the burst script",
        ('pl.lit("branch_movement_untyped")',),
    )
    require_tokens(
        script_source("run_deep_coordination_transitions.py"),
        "the deep-transition script",
        ("PRIMARY_GAP_MINUTES = 5", "INITIAL_BURST_MINUTES = 5", "> gap * 60"),
    )
    episodes = read_csv(
        "outputs/deep_coordination/episode_sessionization_summary.csv",
        ("episode_gap_minutes", "episodes", "mixed_state_episodes"),
    )
    primary = one(episodes, episode_gap_minutes="5")

    entries: list[tuple[str, str, str]] = [
        (
            "Decisive review",
            "A submitted review whose state is APPROVED or CHANGES\\_REQUESTED. Commented and pending reviews are not decisive.",
            "Landmark cohort builder",
        ),
        (
            "Branch movement",
            "A \\texttt{head\\_ref\\_force\\_pushed} timeline event on the PR. It is visible movement of the branch, not a verified repair.",
            "Timeline event filter",
        ),
        (
            "Untyped activity",
            "A post-trigger event row that is not a user account, a mapped product, or another bot. It is the residual class and is always reported together with branch movement.",
            "First-state classifier",
        ),
        (
            "State: user account",
            "The event's GitHub user type is User. User evidence takes precedence over product mapping.",
            "First-state classifier",
        ),
        (
            "State: mapped product",
            "The event is not a User event and its account is on the six-product allowlist.",
            "First-state classifier",
        ),
        (
            "State: other bot",
            "The event's user type is Bot and the account is not on the allowlist.",
            "First-state classifier",
        ),
        (
            "State: branch movement or untyped activity",
            "Every remaining event row, which in this release is branch movement and untyped rows.",
            "First-state classifier",
        ),
        (
            "State: no later action within seven days",
            "No post-burst event occurs inside the seven-day response window.",
            "First-state classifier",
        ),
        (
            "Role: the PR author's own user account",
            "A User account whose login equals the PR author's login.",
            "Response actor roles",
        ),
        (
            "Role: the PR author's product",
            "A mapped product equal to the product attributed to the PR author.",
            "Response actor roles",
        ),
        (
            "Role: the triggering product",
            "A mapped product equal to the product that wrote the trigger.",
            "Response actor roles",
        ),
        (
            "Role: a different mapped product",
            "Any other account on the six-product allowlist.",
            "Response actor roles",
        ),
        (
            "Role: an unmapped bot",
            "A Bot account that is not on the allowlist.",
            "Response actor roles",
        ),
        (
            "Role: another user account",
            "Any other User account.",
            "Response actor roles",
        ),
        (
            "Role: unknown actor",
            "An event with no usable user type. The class is kept so that the seven roles stay exhaustive.",
            "Response actor roles",
        ),
        (
            "Automation episode",
            "A run of post-burst events on one PR in which each event follows the previous one by no more than the gap parameter; a larger gap starts a new episode. The primary gap is five minutes, and the first five minutes after the trigger are excluded before episodes are built.",
            "Episode sessionization",
        ),
        (
            "Episode state",
            "The highest-priority state inside the episode, using the same priority order as the tie rule. At the five-minute gap, "
            + f"{integer(primary['mixed_state_episodes'])} of {integer(primary['episodes'])} episodes mix states.",
            "Episode sessionization",
        ),
    ]
    rows = [(tex(term), definition, tex(source)) for term, definition, source in entries]
    return longtable(
        "Glossary of load-bearing terms, read from the analysis code.",
        "tab:s-glossary",
        r"L{0.22\textwidth}L{0.50\textwidth}L{0.21\textwidth}",
        ("Term", "Definition in the code", "Where it is defined"),
        rows,
        "Each definition is the rule the code applies, not an interpretation of it. The five states are mutually exclusive and cover every PR at every burst threshold. The seven roles are evaluated in the listed order, so the first matching branch wins. None of these labels reports intent, private activity, or whether a review point was resolved.",
    )


def validate(rendered: str) -> None:
    found = {
        token.split("}", 1)[0]
        for token in rendered.split(r"\label{")[1:]
    }
    if found != EXPECTED_LABELS:
        raise ValueError(
            f"Generated label mismatch. Missing={sorted(EXPECTED_LABELS - found)}, "
            f"unexpected={sorted(found - EXPECTED_LABELS)}"
        )
    if rendered.count(r"\begin{table*") != rendered.count(r"\end{table*}"):
        raise ValueError("Unbalanced table* environments")
    if rendered.count(r"\begin{longtable}") != rendered.count(r"\end{longtable}"):
        raise ValueError("Unbalanced longtable environments")
    lowered = rendered.lower()
    for forbidden in ("outputs/", "outputs\\", "scripts/", "scripts\\"):
        if forbidden in lowered:
            raise ValueError(f"Paper-unsafe or invalid generated text contains {forbidden!r}")
    if re.search(r"(?<![a-z])(?:nan|infinity)(?![a-z])", lowered):
        raise ValueError("Generated text contains a non-finite numeric token")


HEADER = "% Generated deterministically; do not edit this file by hand."

# Each group is emitted as its own file so that the appendix can place tables
# beside the prose that explains them. The concatenation of every group is also
# written to OUTPUT, which keeps the single-file product available.
TABLE_GROUPS = (
    ("data", (dataset_table, coverage_table)),
    ("identity", (identity_table, glossary_table)),
    ("cohorts", (funnel_table, specifications_table)),
    (
        "rq1",
        (
            burst_table,
            ties_table,
            ordering_table,
            deep_transition_table,
            falsification_table,
        ),
    ),
    ("rq2", (boundary_table, history_table)),
    (
        "rq3",
        (
            addressed_edge_table,
            gradient_table,
            landmark_route_table,
            exposure_scope_table,
            extensions_table,
            balance_table,
            sensitivity_table,
        ),
    ),
    ("collision", (collision_table,)),
    (
        "external",
        (external_screen_table, external_exact_edge_table, external_attribution_table),
    ),
    ("task_context", (task_context_table,)),
    ("quality", (quality_table, variables_table)),
    ("disposition", (disposition_table,)),
    ("reproduction", (runorder_table, resampling_table)),
)


def group_path(name: str) -> Path:
    return OUTPUT.parent / f"apx_tables_{name}.tex"


def main() -> None:
    groups: list[tuple[str, str]] = []
    for name, builders in TABLE_GROUPS:
        body = "\n\n".join(builder() for builder in builders).rstrip() + "\n"
        groups.append((name, body))

    rendered = HEADER + "\n\n" + "\n\n".join(body for _, body in groups)
    rendered = rendered.rstrip() + "\n"
    validate(rendered)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    for name, body in groups:
        group_path(name).write_text(HEADER + "\n\n" + body, encoding="utf-8", newline="\n")

    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} and {len(groups)} section files "
        f"with {len(EXPECTED_LABELS)} validated table labels."
    )


if __name__ == "__main__":
    main()
