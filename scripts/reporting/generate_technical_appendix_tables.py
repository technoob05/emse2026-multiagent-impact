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
    "tab:s-definitions",
    "tab:s-cohort",
    "tab:s-specifications",
    "tab:s-burst",
    "tab:s-rq1-robustness",
    "tab:s-rq2",
    "tab:s-addressed-edge",
    "tab:s-sensitivity",
    "tab:s-task-context",
    "tab:s-external",
    "tab:s-quality",
    "tab:s-record",
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
    if isinstance(cells, str):
        # Raw TeX passthrough, used for panel rules and panel headings.
        return cells
    return " & ".join(str(cell) for cell in cells) + r" \\"


def panel_heading(columns: int, title: str) -> str:
    return rf"\multicolumn{{{columns}}}{{@{{}}l}}{{\textbf{{{tex(title)}}}}} \\"


def span(count: int, width: str, content: object, first: bool = False, last: bool = False) -> str:
    """A cell that spans `count` adjacent fixed-width columns of a paneled table."""
    prefix = "@{}" if first else ""
    suffix = "@{}" if last else ""
    return rf"\multicolumn{{{count}}}{{{prefix}L{{{width}}}{suffix}}}{{{content}}}"


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
\\footnotesize
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


def paneled_longtable(
    caption: str,
    label: str,
    columns: str,
    column_count: int,
    blocks: Sequence[tuple[str, Sequence[object], Sequence[Sequence[object]]]],
    note: str,
) -> str:
    """Render several panels inside one longtable.

    Each panel carries its own bold title row and its own honest column names, so
    no header string has to describe two different quantities at once. The column
    count is fixed for the whole environment, which LaTeX requires, and a panel
    that needs fewer columns simply leaves its trailing cells empty.
    """
    parts: list[str] = []
    for index, (title, header, rows) in enumerate(blocks):
        if index:
            parts.append(r"\midrule")
        parts.append(panel_heading(column_count, title))
        parts.append(r"\midrule")
        parts.append(row(header))
        parts.append(r"\midrule")
        parts.extend(row(values) for values in rows)
    body = "\n".join(parts)
    # The panels carry their own headings, so no column header is repeated on a
    # continuation page; only the unnumbered continuation caption is emitted.
    return f"""\\FloatBarrier
\\needspace{{8\\baselineskip}}
\\begingroup
\\footnotesize
\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{longtable}}{{@{{}}{columns}@{{}}}}
\\caption{{{tex(caption)}}}\\label{{{label}}}\\\\
\\endfirsthead
\\caption*{{{tex(caption)} (continued)}}\\\\
\\endhead
\\toprule
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


def release_table() -> str:
    inventory = read_csv(
        "outputs/tables/dataset_table_inventory.csv",
        ("table", "scope", "grain", "rows", "columns", "role"),
    )
    coverage = read_csv(
        "outputs/tables/dataset_join_coverage.csv",
        ("feature_group", "event_rows", "matched_pr_ids", "coverage_pct_of_aidev_pop", "orphan_pr_ids"),
    )
    rows: list[tuple[str, ...]] = []
    for item in inventory:
        rows.append(
            (
                tex("Release inventory"),
                breakable_identifier(item["table"]),
                tex(item["scope"].replace("AIDev-pop (>100 stars)", "Rich layer")),
                tex(item["grain"]),
                integer(item["rows"]),
                tex(f"{integer(item['columns'])} fields; {item['role']}"),
            )
        )
    for item in coverage:
        rows.append(
            (
                tex("PR coverage"),
                tex(item["feature_group"]),
                tex("Rich layer"),
                tex("Linked event or feature rows"),
                integer(item["event_rows"]),
                tex(
                    f"{integer(item['matched_pr_ids'])} matched PRs; "
                    f"{number(item['coverage_pct_of_aidev_pop']):.2f}% PR coverage; "
                    f"{integer(item['orphan_pr_ids'])} orphan PR IDs"
                ),
            )
        )
    return longtable(
        "Release inventory, units, analytical roles, and event-table coverage.",
        "tab:s-dataset",
        r"L{0.12\textwidth}L{0.20\textwidth}L{0.07\textwidth}L{0.13\textwidth}L{0.09\textwidth}L{0.31\textwidth}",
        ("Block", "Table or feature group", "Scope", "Unit", "Rows", "Fields, coverage, and role"),
        rows,
        "The rich layer contains repositories with more than 100 stars. Inventory row counts come from Parquet metadata, so large content tables are not expanded in memory. The coverage block describes the 361,296 AIDev-pop pull requests: coverage means that a pull request has at least one linked row, and inline comments resolve through their submitted-review identifier before joining to the pull request.",
    )


def identity_rows() -> list[tuple[str, str]]:
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
    return rows


def funnel_rows() -> list[tuple[str, ...]]:
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
    return [(tex(stage), f"{count:,}", tex(denominator), percent(share)) for stage, count, denominator, share in records]


FUNNEL_NOTE = "An exact parent reply is defined only for an inline trigger. The repeated rows make the full-cohort and eligible denominators explicit."


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


def rq1_placebo_rows() -> list[tuple[str, ...]]:
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
    episodes = read_csv(
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

    selected = [item for item in transitions if int(number(item["washout_minutes"])) == 5]
    if len(selected) != 6:
        raise ValueError("Expected six deep-transition states after the five-minute washout")

    rows: list[tuple[str, ...]] = []
    for item in selected:
        rows.append(
            (
                tex("Deep transition"),
                tex(f"Next state: {STATE_LABELS[item['next_owner_state']]}"),
                integer(item["prs"]),
                percent(item["share"]),
                "--",
                ci_percent(item["repository_cluster_ci_low"], item["repository_cluster_ci_high"]),
            )
        )
    p = one(placebo, washout_minutes="5")
    rows.extend(
        [
            (
                tex("Deep transition"),
                tex("Same-product continuation among later mapped events: observed"),
                integer(p["eligible_prs"]),
                percent(p["observed_same_product_share"]),
                "--",
                "--",
            ),
            (
                tex("Deep transition"),
                tex("Same-product continuation: random-order expectation"),
                integer(p["eligible_prs"]),
                percent(p["random_order_expected_share"]),
                "--",
                "--",
            ),
            (
                tex("Deep transition"),
                tex("Observed minus random-order expectation"),
                integer(p["eligible_prs"]),
                "--",
                pp(p["observed_minus_random_order"]),
                ci_pp(p["repository_cluster_difference_ci_low"], p["repository_cluster_difference_ci_high"]),
            ),
        ]
    )
    for state in (1, 2, 3, 4):
        observed = one(
            episodes,
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
                tex("Escalation placebo"),
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
                tex("Ownership persistence"),
                tex(f"Visible next action: {metric_labels[metric]}"),
                tex("3,237 start PRs"),
                tex(f"user {percent(item['user_first_estimate'])}; product {percent(item['mapped_first_estimate'])}"),
                pp(item["user_minus_mapped"]),
                ci_pp(item["repository_cluster_ci_low"], item["repository_cluster_ci_high"]),
            )
        )
    return rows


PLACEBO_NOTE = (
    "Deep-transition next-state shares use 924 mapped-first PRs; the same-product placebo uses 495 PRs with a later mapped-product event and preserves each PR's future product composition. Escalation rows compare the observed user-next share with a within-PR order permutation. Ownership rows condition on a visible next action; their difference column is user-first minus mapped-first. Same-layer continuation and cross-layer bounce show no clear group difference, while exact owner repetition is higher after a mapped-product first state."
)


def boundary_rows() -> list[tuple[str, ...]]:
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
    return rows


BOUNDARY_NOTE = "Pairs also match repository, author product, trigger source, and month, then use nearest trigger time without replacement. Difference is cross-product minus same-product."


def history_rows() -> list[tuple[str, ...]]:
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
    return rows


HISTORY_NOTE = "Prior history requires the same account, the same repository, a different PR, and a submitted review strictly before the cross-product trigger. It is observable public history, not verified memory retrieval."


def rq2_table() -> str:
    history = [
        (population, account_rows, repositories, prior, median, "")
        for population, account_rows, repositories, prior, median in history_rows()
    ]
    return paneled_longtable(
        "RQ2: matched cross- versus same-product comparison and prior review history.",
        "tab:s-rq2",
        r"L{0.27\textwidth}L{0.14\textwidth}L{0.07\textwidth}L{0.09\textwidth}L{0.13\textwidth}L{0.22\textwidth}",
        6,
        (
            (
                "Panel A. Exact-author matched cross- versus same-product comparison",
                (
                    "Outcome",
                    "Pairs",
                    "Cross (\\%)",
                    "Same (\\%)",
                    "Difference (pp)",
                    "Repository-cluster 95\\% interval",
                ),
                boundary_rows(),
            ),
            (
                "Panel B. Strict prior same-repository review history",
                (
                    "Population",
                    "Account--PR rows",
                    "Repos",
                    "With prior history (\\%)",
                    "Median prior PRs",
                    "",
                ),
                history,
            ),
        ),
        "Panel A is the exact-author matched trigger comparison. "
        + BOUNDARY_NOTE
        + " Panel B reports prior review history across user-account populations, and its median prior-PR count is taken among accounts with prior history. "
        + HISTORY_NOTE,
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
    gradient = read_csv(
        "outputs/addressed_edge_specificity/four_state_response_gradient.csv",
        ("contrast", "threshold_hours", "estimate", "ci_low", "ci_high", "n_prs", "repositories"),
    )
    gradient_denominators = read_csv(
        "outputs/addressed_edge_specificity/denominators.csv",
        ("threshold_hours", "population", "group", "prs", "later_merge_rate"),
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

    def gradient_group(group: str) -> Mapping[str, str]:
        return one(
            gradient_denominators,
            threshold_hours="48",
            population="full_landmark_cohort",
            group=group,
        )

    for contrast, label, compared, reference in (
        ("exact_edge_vs_no_visible_activity", "Gradient: exact edge vs no visible activity", "exact_edge", "no_visible_activity"),
        ("nonexact_discussion_vs_no_visible_activity", "Gradient: non-exact discussion vs no visible activity", "nonexact_discussion_only", "no_visible_activity"),
        ("movement_only_vs_no_visible_activity", "Gradient: movement only vs no visible activity", "movement_only", "no_visible_activity"),
        ("exact_edge_vs_nonexact_discussion", "Gradient: exact edge vs non-exact discussion", "exact_edge", "nonexact_discussion_only"),
    ):
        item = one(gradient, contrast=contrast, threshold_hours="48")
        compared_group = gradient_group(compared)
        reference_group = gradient_group(reference)
        rows.append(
            (
                "48 h",
                tex(label),
                f"{integer(compared_group['prs'])} vs {integer(reference_group['prs'])}",
                f"{percent(compared_group['later_merge_rate'])} / {percent(reference_group['later_merge_rate'])}",
                pp(item["estimate"]),
                ci_pp(item["ci_low"], item["ci_high"]),
            )
        )
    return longtable(
        "Exact-parent addressed edge, specificity controls, and the four-state gradient at the 48-hour landmark.",
        "tab:s-addressed-edge",
        r"L{0.08\textwidth}L{0.26\textwidth}L{0.10\textwidth}L{0.15\textwidth}L{0.13\textwidth}L{0.20\textwidth}",
        ("Reply window", "Specification or contrast", "Compared PRs", "Raw merge: compared / reference (\\%)", "Adjusted difference (pp)", "95\\% interval"),
        rows,
        "The main models use 1,067 inline-trigger PRs in 469 repositories that were open at hour 48 and had a complete 30-day horizon. Specificity rows compare 109 exact-edge PRs with 506 PRs that had public discussion but no exact edge. The gradient block is one model over the full 1,067-PR cohort in 469 repositories that places all four mutually exclusive post-trigger states against the no-visible-activity reference, with the same pre-trigger controls; its movement-only group holds 26 PRs, so that interval is wide and its point estimate is not a ranking. The active-discussion subset remains the primary specificity contrast because it does not compare an active PR with a silent one. This post-trigger discussion control is a structural falsification check, not a causal or semantic-resolution estimate.",
    )


def rq3_robustness_table() -> str:
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
    balance = read_csv(
        "outputs/addressed_edge_landmark/pretrigger_balance.csv",
        ("threshold_hours", "variable", "exposed_mean", "unexposed_mean", "standardized_mean_difference"),
    )
    scores = read_csv(
        "outputs/addressed_edge_specificity/propensity_score_diagnostics.csv",
        ("group", "quantile", "propensity_score"),
    )
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
    history_robustness = read_csv(
        "outputs/rq3_extensions/history_moderation_robustness.csv",
        ("check", "detail", "estimate", "ci_low", "ci_high"),
    )

    role_labels = {
        "author_account": "PR author's own user account",
        "other_human": "Another user account",
        "triggering_reviewer_brand": "The triggering product itself",
        "other_bot": "An unmapped bot",
        "author_agent_brand": "The PR author's product",
        "other_agent_brand": "A different mapped product",
    }
    control_labels = {
        "pre_trigger_decisive_review": "Pre-trigger decisive review",
        "pre_trigger_force_push": "Pre-trigger branch movement",
        "pre_trigger_user_event": "Pre-trigger user event",
    }
    hazard_labels = {
        "A_baseline_hazard_only": "Time only",
        "B_products_and_month": "Products and month",
        "C_full_pretrigger": "Full pre-trigger controls",
    }
    class_labels = {
        "edge_by_known_reviewer": "Edge written by a prior reviewer of this repository",
        "edge_by_newcomer": "Edge written by an account new to this repository",
        "edge_by_automation": "Edge written by automation",
    }

    rows: list[tuple[str, ...]] = []

    for item in selection:
        rows.append(
            (
                tex("Cohort restriction"),
                tex(item["stage"]),
                "--",
                "--",
                f"{integer(item['prs'])} PRs, {percent(item['share_of_inline_triggers'])}\\% of cross-product inline triggers",
            )
        )

    for item in composition:
        label = role_labels.get(item["response_actor_role"], str(item["response_actor_role"]))
        rows.append(
            (
                tex("Who writes the edge"),
                tex(label),
                "--",
                "--",
                plural(item["events"], "event")
                + f", {percent(item['share_of_exposure_events'])}\\% of exposure events, on "
                + plural(item["prs"], "PR"),
            )
        )

    for item in definitions:
        estimate = item["estimate"].strip()
        rows.append(
            (
                tex("Exposure definition"),
                tex(item["definition"]),
                pp(estimate) if estimate else "--",
                ci_pp(item["ci_low"], item["ci_high"]) if estimate else "--",
                tex(
                    f"{integer(item['exposed_prs'])} exposed PRs, raw later merge "
                    f"{percent(item['exposed_raw_merge_rate'])}%"
                    if estimate
                    else f"{integer(item['exposed_prs'])} exposed PRs; not modelled: too few"
                ),
            )
        )

    for threshold in (1, 6, 24, 48):
        for variable, label in BALANCE_VARIABLE_LABELS.items():
            item = one(balance, threshold_hours=str(threshold), variable=variable)
            rows.append(
                (
                    tex("Pre-trigger balance"),
                    tex(f"{label} ({threshold} h)"),
                    f"{number(item['standardized_mean_difference']):+.3f}",
                    "--",
                    tex(
                        f"edge mean {number(item['exposed_mean']):.3f}; "
                        f"no-edge mean {number(item['unexposed_mean']):.3f}"
                    ),
                )
            )
    for quantile in ("0.0", "0.05", "0.25", "0.5", "0.75", "0.95", "1.0"):
        edge = one(scores, group="exact_edge", quantile=quantile)
        control = one(scores, group="nonexact_discussion_only", quantile=quantile)
        rows.append(
            (
                tex("Propensity overlap"),
                tex(f"Propensity score at the {percent(quantile, 0)} percentile (48 h)"),
                "--",
                "--",
                tex(
                    f"edge {number(edge['propensity_score']):.3f}; "
                    f"no-edge {number(control['propensity_score']):.3f}"
                ),
            )
        )

    for threshold in (1, 6, 24, 48):
        item = one(evalues, threshold_hours=str(threshold))
        rows.append(
            (
                tex("E-value"),
                tex(f"{threshold} h reply window"),
                pp(item["adjusted_risk_difference"]),
                ci_pp(item["ci_low"], item["ci_high"]),
                tex(
                    f"{integer(item['exposed_prs'])} exposed PRs; risk ratio "
                    f"{number(item['approximate_risk_ratio']):.2f}; E-value "
                    f"{number(item['e_value_point']):.2f}, limit "
                    f"{number(item['e_value_limit']):.2f}"
                ),
            )
        )

    for prevalence in ("0.2", "0.4"):
        item = one(frontier, prevalence_difference=prevalence)
        rows.append(
            (
                tex("Tipping point"),
                tex(f"One binary factor {percent(prevalence, 0)} pp more common among edge PRs, 48 h"),
                "--",
                "--",
                tex(
                    f"must itself carry {percent(item['outcome_difference_to_remove_point_estimate'])} pp "
                    f"of later merge to remove the point estimate, and "
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
                    tex("Negative control"),
                    tex(f"{label} ({threshold} h)"),
                    pp(item["estimate"]),
                    ci_pp(item["ci_low"], item["ci_high"]),
                    tex(
                        f"{integer(item['n_prs'])} PRs; "
                        + (
                            "interval covers the null"
                            if passes
                            else "interval excludes the null: residual pre-trigger confounding"
                        )
                    ),
                )
            )

    for threshold in (1, 6, 24, 48):
        item = one(permutation, threshold_hours=str(threshold))
        rows.append(
            (
                tex("Randomisation, unconditional"),
                tex(f"{threshold} h reply window"),
                pp(item["observed_estimate"]),
                ci_pp(item["permutation_quantile_025"], item["permutation_quantile_975"]),
                tex(
                    f"two-sided p = {number(item['permutation_p_value_two_sided']):.3f} over "
                    f"{integer(item['permutations'])} within-repository permutations across "
                    f"{integer(item['repositories_with_within_exposure_variation'])} repositories"
                ),
            )
        )

    test = conditional[0]
    rows.append(
        (
            tex("Randomisation, conditional"),
            tex("Re-randomisable repositories, with repository fixed effects"),
            pp(test["observed_estimate"]),
            "--",
            tex(
                f"{integer(test['n_prs'])} PRs in {integer(test['repositories'])} repos; "
                f"reference mean {pp(test['permutation_mean'])} pp over "
                f"{integer(test['permutations'])} permutations; two-sided p = "
                f"{number(test['permutation_p_value_two_sided']):.3f}"
            ),
        )
    )

    for key, label in hazard_labels.items():
        item = one(hazard, specification=key)
        rows.append(
            (
                tex("Whole-population hazard"),
                tex(label),
                f"{number(item['hazard_odds_ratio']):.2f}",
                tex(f"[{number(item['or_ci_low']):.2f}, {number(item['or_ci_high']):.2f}]"),
                tex(
                    f"odds ratio for merging in the next interval; "
                    f"{integer(item['prs'])} PRs, {integer(item['person_period_rows'])} periods; "
                    f"p = {number(item['p_value']):.2g}"
                ),
            )
        )

    for key, label in class_labels.items():
        item = one(classes, edge_class=key)
        rows.append(
            (
                tex("Who wrote the edge"),
                tex(label),
                pp(item["estimate"]),
                ci_pp(item["ci_low"], item["ci_high"]),
                tex(
                    f"{integer(item['prs'])} PRs, raw later merge "
                    f"{percent(item['raw_later_merge_rate'])}%, against the no-edge reference"
                ),
            )
        )

    for item in history_robustness:
        rows.append(
            (
                tex("Who wrote the edge"),
                tex(f"Prior reviewer minus newcomer: {item['check'].lower()}"),
                pp(item["estimate"]),
                ci_pp(item["ci_low"], item["ci_high"]),
                tex(item["detail"]),
            )
        )

    return longtable(
        "RQ3 robustness: cohort scope, exposure composition, measured balance, sensitivity bounds, and design extensions.",
        "tab:s-sensitivity",
        r"L{0.14\textwidth}L{0.27\textwidth}L{0.08\textwidth}L{0.14\textwidth}L{0.30\textwidth}",
        (
            "Check",
            "Item",
            "Estimate",
            "95\\% interval or band",
            "Size and detail",
        ),
        rows,
        "Unless a row says otherwise, every check uses the 1,067-PR inline-trigger landmark cohort and the pre-trigger adjusted specification. Cohort-restriction rows show that the landmark cohort is the slower-resolving remainder of the cross-product inline-trigger population. The exposure rule requires a reply whose parent identifier is the trigger's own identifier; it does not require another product to write it, and the composition rows report who actually wrote the 128 exposure events on the 109 exposed PRs. Exposure-definition rows refit the primary model on the same cohort under stricter definitions. A standardized mean difference is the group difference divided by the pooled standard deviation; every value is below 0.16 in absolute size, and balance on measured variables says nothing about unmeasured structure such as task difficulty. E-values are computed on an approximate risk-ratio scale from the adjusted risk difference and the unexposed later-merge rate; they state the minimum association an unmeasured factor would need with both the exact edge and later merge, beyond the measured controls. Negative-control outcomes were complete before the trigger, so the exposure cannot produce them and a non-null estimate signals residual confounding rather than an effect. The unconditional randomisation rows permute across the whole cohort and their bracketed pair is the 2.5th to 97.5th percentile of the permuted reference distribution, not a confidence interval; that distribution is not centred on zero because 423 of 469 repositories contain no exposure variation. The conditional row, which is the one quoted in the article, uses only repositories containing both exposed and unexposed PRs and adds repository fixed effects, so its reference is centred. The whole-population rows drop the hour-48 restriction: every cross-product inline-trigger PR with a complete 30-day horizon is followed from its trigger, follow-up is split into eleven intervals, and the exact addressed edge enters as a time-varying covariate, so a PR contributes unexposed periods until its own first exact reply; the estimate is an odds ratio from a pooled logistic model with interval indicators and repository-clustered standard errors. The edge-class rows split the 109 exposed PRs by the account that wrote the first exact reply, using the same strict prior-history rule as the RQ2 analysis, and the fixed-effect row is the decisive one: the gap between a prior reviewer and a newcomer is largely a difference between repositories, not within them, so these rows describe where the signal sits and do not identify a mechanism. None of these checks identifies a causal effect.",
    )


def landmark_route_rows() -> list[tuple[str, ...]]:
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
    return rows


ROUTE_NOTE = "The reference is automation with no later user event. Adjustment uses only pre-trigger activity and trigger context. Routes are observed markers, not assigned treatments."


def cohort_table() -> str:
    funnel = [(stage, prs, denominator, share, "", "") for stage, prs, denominator, share in funnel_rows()]
    return paneled_longtable(
        "Cohort funnel and the 48-hour ownership routes.",
        "tab:s-cohort",
        r"L{0.21\textwidth}L{0.07\textwidth}L{0.18\textwidth}L{0.09\textwidth}L{0.14\textwidth}L{0.23\textwidth}",
        6,
        (
            (
                "Panel A. Participation-to-addressed-edge denominator funnel",
                ("Stage", "PRs", "Denominator", "Share (\\%)", "", ""),
                funnel,
            ),
            (
                "Panel B. Forty-eight-hour ownership routes and later integration",
                (
                    "Route",
                    "PRs",
                    "Later merge (\\%)",
                    "Median first action (h)",
                    "Adjusted difference (pp)",
                    "Repository-cluster 95\\% interval",
                ),
                landmark_route_rows(),
            ),
        ),
        "Panel A is the denominator funnel. "
        + FUNNEL_NOTE
        + " Panel B reports the 48-hour ownership routes. "
        + ROUTE_NOTE,
    )


def plural(value: object, noun: str) -> str:
    count = int(round(number(value)))
    return f"{count:,} {noun}" + ("" if count == 1 else "s")


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
        r"L{0.24\textwidth}L{0.28\textwidth}L{0.13\textwidth}L{0.30\textwidth}",
        ("Group", "Condition", "Answered", "Detail"),
        rows,
        "The exposure is a pre-trigger property of the change: the pull request body references an issue. The outcome is a later inline comment whose reply target is the trigger comment, strictly after it and within 48 hours, rebuilt from the raw comment table so that both reviewer relations are measured the same way. The population is restricted to triggers that open their own thread, because a mid-thread trigger cannot receive such a reply at all; that restriction removes 0.4 per cent of cross-product triggers but 46 per cent of same-product ones, so leaving it in would compare a possible outcome against an impossible one. The unrestricted rows are reported beside the restricted ones. The release carries no timestamp for the issue link and pull request bodies can be edited, so the link is assumed rather than proven to precede the trigger. Nothing here identifies a causal effect.",
    )


def collision_rows() -> list[tuple[str, ...]]:
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
    return rows


COLLISION_NOTE = "Structural co-location and timing do not establish semantic duplication, contradiction, correctness, repair, or coordination. The product-pair generality gate fails because the largest pair exceeds 50 percent."


def external_screen_rows() -> tuple[list[tuple[str, ...]], str]:
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
    funnel = read_csv(
        "protocol/swe_review_chat_exact_edge_funnel_20260826.csv",
        ("order", "stage", "count"),
    )
    pilot = read_json("protocol/swe_review_chat_exact_edge_pilot_20260826.json")
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
    rows: list[tuple[str, ...]] = []
    for dataset_id, edge, role in selected:
        item = one(registry, dataset_id=dataset_id)
        rows.append(
            (
                tex("Evidence ladder"),
                tex(item["dataset"]),
                tex(item["unit_grain"]),
                tex(f"exact edge: {edge}"),
                tex(role),
            )
        )

    by_stage = {item["stage"]: item for item in funnel}

    def count(stage: str) -> str:
        if stage not in by_stage:
            raise ValueError(f"Missing SWE-Review-Chat funnel stage: {stage}")
        return integer(by_stage[stage]["count"])

    child_counts = pilot["extraction"]["source_child_relation_to_parent_counts"]
    user_children = int(child_counts.get("user_unmapped_product", 0))
    same_children = int(child_counts.get("same_as_parent_product", 0))
    different_children = int(child_counts.get("different_from_parent_product", 0))
    for stage_label, value, meaning in (
        ("Public PR rows scanned", count("dataset_pr_rows"), "Available corpus"),
        ("PRs whose author maps by the frozen exact alias list", count("exact_alias_mapped_author_prs"), "Product-aware author support"),
        ("PRs with a cross-product inline parent", count("prs_with_any_cross_product_inline_parent"), "Candidate trigger support"),
        ("PRs where such a parent has a nested reply", count("prs_where_qualifying_parent_has_nested_reply"), "Seven candidate PRs before overlap removal"),
        ("Nested children before overlap removal", f"{integer(user_children)} / {integer(same_children)} / {integer(different_children)}", "Unmapped user / same product / different product"),
        ("Candidate PRs outside the AIDev full corpus", count("non_aidev_candidate_prs"), "No independent cohort remains"),
        ("REST-validated 48-hour landmark PRs", count("rest_validated_landmark_eligible_prs"), "Replication gate fails"),
    ):
        rows.append(
            (
                tex("SWE-Review-Chat replication gate"),
                tex(stage_label),
                value,
                "--",
                tex(meaning),
            )
        )

    overlap = one(coverage, stage="PR also appears in external A2A cross-product cohort")
    agreement = one(coverage, stage="Exact pair agreement conditional on overlapping PR")
    exposed = one(coverage, stage="Exact-edge exposed PRs in exact-pair overlap")
    timestamp_rows = one(temporal, metric="exact-pair rows with both trigger timestamps")
    timestamp_match = one(temporal, metric="absolute timestamp difference within five minutes")
    raw = one(models, specification="unadjusted")
    adjusted = one(models, specification="pretrigger_adjusted")
    for check, size, observed, use in (
        ("PR overlap", integer(overlap["prs"]), f"{percent(overlap['share_of_landmark'])}\\% of landmark cohort", "Coverage only"),
        ("Exact author--reviewer pair agrees", integer(agreement["prs"]), f"{percent(agreement['share_of_landmark'])}\\% of overlapping PRs", "Supports product attribution"),
        ("Trigger time agrees within five minutes", integer(timestamp_rows["value"]), f"{percent(timestamp_match['value'])}\\%", "Supports event anchoring"),
        ("Exact-edge exposed PRs", integer(exposed["prs"]), f"{percent(exposed['share_of_landmark'])}\\% of exact-pair overlap", "Too few for replication"),
        ("Raw later-merge difference", integer(raw["n_prs"]), f"{pp(raw['estimate'])} pp", f"95\\% interval {ci_pp(raw['ci_low'], raw['ci_high'])}"),
        ("Pre-trigger-adjusted difference", integer(adjusted["n_prs"]), f"{pp(adjusted['estimate'])} pp", f"95\\% interval {ci_pp(adjusted['ci_low'], adjusted['ci_high'])}"),
    ):
        rows.append((tex("CodAGE attribution concordance"), tex(check), size, observed, use))

    note = (
        f"The registry contains {len(registry)} screened candidates. Sources are not pooled merely to add rows: a source must preserve the PR, event time, actor, review batch, exact reply parent, and later-state horizon before it can reproduce the declared topology. In the replication-gate block all seven pre-exclusion candidate PRs already occur in the AIDev full corpus, and no GitHub comment or PR body was exported; zero disjoint support is a failed replication gate, not evidence that exact public connections never occur. The concordance block uses an external cohort that was released independently but observes overlapping public GitHub PRs; its 119-PR exact-pair overlap contains only nine exposed PRs, so the merge rows are an appendix sensitivity, not an independent outcome replication or a causal estimate."
    )
    return rows, note


def external_table() -> str:
    screen_rows, screen_note = external_screen_rows()
    # Panel A needs three wide fields rather than five narrow ones, so its first
    # and last fields each span two of the fixed columns.
    wide = r"0.376\textwidth"
    tail = r"0.386\textwidth"
    collision = [
        (
            span(2, wide, quantity, first=True),
            observed,
            span(2, tail, interpretation, last=True),
        )
        for quantity, observed, interpretation in collision_rows()
    ]
    collision_header = (
        span(2, wide, "Quantity or gate", first=True),
        "Observed",
        span(2, tail, "Interpretation or status", last=True),
    )
    return paneled_longtable(
        "Structural overlap gates and external evidence screening.",
        "tab:s-external",
        r"L{0.15\textwidth}L{0.21\textwidth}L{0.20\textwidth}L{0.11\textwidth}L{0.26\textwidth}",
        5,
        (
            (
                "Panel A. Structural same-locus review overlap and frozen semantic gates",
                collision_header,
                collision,
            ),
            (
                "Panel B. External evidence screening",
                ("Block", "Item", "Unit or count", "Observed", "Role or meaning"),
                screen_rows,
            ),
        ),
        "Panel A reports structural same-locus review overlap and the frozen semantic gates. "
        + COLLISION_NOTE
        + " Panel B is the external evidence ladder, the failed replication gate, and the independent attribution concordance. "
        + screen_note,
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
    rows = [(tex("Validation gate"), tex(name), tex(status), tex(value)) for name, status, value in checks]

    schema = read_json("outputs/addressed_edge_landmark/schema.json")
    columns = schema.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("The landmark schema has no column list")
    for entry in columns:
        availability = entry["available_when"]
        if availability not in AVAILABILITY_LABELS:
            raise ValueError(f"Unknown leakage tag: {availability}")
        dtype = str(entry["dtype"])
        rows.append(
            (
                tex("Cohort column"),
                breakable_identifier(entry["column"])
                + tex(f" ({'Datetime (UTC)' if dtype.startswith('Datetime') else dtype})"),
                tex(AVAILABILITY_LABELS[availability]),
                definition_text(entry["definition"]),
            )
        )

    return longtable(
        f"Validation gates and the {len(columns)}-column variable dictionary for the landmark cohort.",
        "tab:s-quality",
        r"L{0.10\textwidth}L{0.31\textwidth}L{0.15\textwidth}L{0.38\textwidth}",
        ("Block", "Gate or column", "Status or availability", "Observed or definition"),
        rows,
        "PASS means that the frozen automated check met its declared contract. LIMIT identifies missing measurement coverage rather than a failed computation. In the column block, the availability value is the leakage tag stored with the cohort itself: only columns available at or before the trigger enter the primary model, columns available after the trigger enter the secondary route decomposition and the exposure definition, and columns tagged as outcome are read only after hour 48. Datetime columns are microsecond UTC timestamps. The dictionary records where each value can be observed, not whether it is a good measure of the thing it is named after.",
    )


def disposition_rows() -> list[tuple[str, ...]]:
    data = read_csv(
        "protocol/experiment_disposition_20260826.csv",
        ("experiment_or_claim", "status", "reason"),
    )
    allowed = {"MAIN", "SECONDARY", "APPENDIX", "REJECT", "PENDING"}
    unknown = {item["status"] for item in data} - allowed
    if unknown:
        raise ValueError(f"Unknown experiment disposition(s): {sorted(unknown)}")
    return [(tex(item["experiment_or_claim"]), tex(item["status"]), tex(item["reason"])) for item in data]


DISPOSITION_NOTE = "MAIN enters the article's core story; SECONDARY supports that story; APPENDIX is informative but not a headline; REJECT is retained as a falsification result; PENDING requires evidence not yet available."


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

    def model_row(label: str, exposure: str, item: Mapping[str, str]) -> tuple[str, ...]:
        return (
            tex(label),
            tex("outcome ") + breakable_code("merged_from_48h_to_30d") + tex("; exposure ") + breakable_code(exposure),
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
                tex("outcome ") + breakable_code("merged_from_48h_to_30d") + tex("; exposure ") + breakable_code("ownership_route_48h"),
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
                tex("outcome ") + breakable_code("prior_different_pr_reviewer") + tex("; exposure ") + breakable_code(term),
                tex(CLUSTERED_CORRECTED_ERRORS),
                f"{integer(item['n'])} / {integer(item['repositories'])}",
                breakable_code(formula),
            )
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
    for analysis, unit, draws, seed, method in records:
        rows.append(
            (
                tex(analysis),
                tex(f"resampling unit: {unit}"),
                tex("no resampling" if draws == "--" else f"{draws}; seed {seed}"),
                "--",
                tex(method),
            )
        )

    return longtable(
        "Named estimation specifications and the resampling settings behind every reported interval.",
        "tab:s-specifications",
        r"L{0.16\textwidth}L{0.16\textwidth}L{0.15\textwidth}L{0.08\textwidth}L{0.38\textwidth}",
        ("Analysis", "Design", "Uncertainty", "PRs / repos", "Formula or interval method"),
        rows,
        "Every model row is a linear probability model fitted by ordinary least squares, with standard errors clustered on the repository. Formulas are stored with the analysis products themselves, except the two route rows and the two prior-history rows, whose formulas are read back from the analysis code. The reply-window variants at 1, 6, and 24 hours refit the same formula with the exposure term for that window. Resampling draw counts are not uniform across the analyses, so they are listed rather than summarized; every seed is fixed, and offsets are added so that separate quantities inside one script do not reuse one draw sequence. A percentile band is the 2.5th and 97.5th percentile of the draw distribution. The final row records that the regression intervals come from a clustered normal approximation, which is why the exact-edge estimate is also checked by permutation. A specification describes the fit; it does not claim that the fit identifies an effect.",
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
    "run_merge_curves.py": ("Cumulative merge curves for the exact-edge contrast", "outputs/merge_curves/cumulative_merge.csv"),
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


def runorder_rows() -> list[tuple[str, ...]]:
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
    return rows


RUNORDER_NOTE = "The order is read from the repository README, so this table cannot drift from the documented sequence. The expected-row column names one frozen product per step where a stable count exists; a dash means the step writes figures, validation logs, or binary tables instead. A rerun that changes a listed count is a signal to compare inputs, not to accept the new number."


def record_table() -> str:
    steps = [
        (index, command, expected, produces)
        for index, command, produces, expected in runorder_rows()
    ]
    # Panel B has no step number, so its claim spans the step and command columns
    # instead of leaving a blank cell in front of every row.
    claim_width = r"0.346\textwidth"
    dispositions = [
        (span(2, claim_width, claim, first=True), status, reason)
        for claim, status, reason in disposition_rows()
    ]
    return paneled_longtable(
        "Ordered reproduction contract and the disposition of every experiment.",
        "tab:s-record",
        r"L{0.06\textwidth}L{0.27\textwidth}L{0.12\textwidth}L{0.50\textwidth}",
        4,
        (
            (
                "Panel A. Ordered reproduction contract with frozen row counts",
                ("Step", "Command", "Expected rows", "Produces"),
                steps,
            ),
            (
                "Panel B. Disposition of every experiment and claim",
                (span(2, claim_width, "Experiment or claim", first=True), "Status", "Reason"),
                dispositions,
            ),
        ),
        "Panel A is the ordered reproduction contract. "
        + RUNORDER_NOTE
        + " Panel B is the disposition of every experiment and claim after robustness and construct checks. "
        + DISPOSITION_NOTE,
    )


def ordering_rows() -> list[tuple[str, ...]]:
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
    unit_labels = {"repository": "dropping one repository", "product_pair": "dropping one ordered product pair"}
    rows: list[tuple[str, ...]] = []

    for threshold in (0, 1, 5, 10, 30):
        item = one(diagnostics, burst_threshold_minutes=str(threshold))
        rows.append(
            (
                tex("Tie diagnostic"),
                str(threshold),
                tex(
                    f"Tied first timestamps among {integer(item['post_burst_action_prs'])} PRs "
                    "with a post-burst action"
                ),
                "--",
                integer(item["first_timestamp_tie_prs"]),
                tex(
                    f"{integer(item['mixed_state_tie_prs'])} mixed-state ties; "
                    f"largest tie group {integer(item['maximum_events_at_first_timestamp'])}"
                ),
            )
        )

    for unit in ("repository", "product_pair"):
        for threshold in (0, 1, 5, 10, 30):
            item = one(robustness, burst_threshold_minutes=str(threshold), exclusion_unit=unit)
            gates_hold = (
                str(item["user_exceeds_mapped_in_every_exclusion"]).strip().lower() == "true"
                and str(item["no_action_is_largest_in_every_exclusion"]).strip().lower() == "true"
            )
            rows.append(
                (
                    tex("Leave-one-out ordering gate"),
                    str(threshold),
                    tex(f"User minus mapped product, {unit_labels[unit]}"),
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
                    tex("Leave-one-out share range"),
                    "5",
                    tex(f"{STATE_LABELS[state]}, {unit_labels[unit]}"),
                    percent(item["full_share"]),
                    f"{percent(item['minimum_loo_share'])} to {percent(item['maximum_loo_share'])}",
                    tex(f"largest shift {number(item['maximum_absolute_shift_percentage_points']):.2f} pp"),
                )
            )
    return rows


ORDERING_NOTE = (
    "The priority order is user account, then mapped product, then other bot, then branch movement or untyped activity. Ties are common because many events share a whole-second timestamp, but a tie changes the assigned state only when the tied events fall in different states. Exactly one mixed-state tie occurs, at the zero-minute threshold, and none occurs at any positive threshold. The order favours the user-account state, which is the state the RQ1 ordering claim rests on, so the diagnostic is reported rather than assumed harmless. The gate block drops one repository, or one ordered author--reviewer product pair, at a time and refits the ordering; two gates are checked in every exclusion, namely that the user-account share stays above the mapped-product share and that no later action within seven days stays the largest state. The share-range block reports the range for each state at the primary five-minute threshold. These checks show that the ordering is not carried by one repository or one product pair. They do not remove selection into the cohort."
)


def rq1_robustness_table() -> str:
    ordering = [
        (check, quantity, threshold, full, spread, gate)
        for check, threshold, quantity, full, spread, gate in ordering_rows()
    ]
    return paneled_longtable(
        "RQ1 robustness: ordering diagnostics and order placebos.",
        "tab:s-rq1-robustness",
        r"L{0.16\textwidth}L{0.28\textwidth}L{0.07\textwidth}L{0.12\textwidth}L{0.13\textwidth}L{0.16\textwidth}",
        6,
        (
            (
                "Panel A. Ordering diagnostics and leave-one-out checks",
                ("Check", "Quantity", "Burst (min)", "Full (\\%)", "Range or count", "Gate, shift, or diagnostic"),
                ordering,
            ),
            (
                "Panel B. Order placebos",
                ("Block", "Test or quantity", "At risk", "Observed (\\%)", "Null or difference (pp)", "95\\% interval"),
                rq1_placebo_rows(),
            ),
        ),
        "Panel A covers tie diagnostics and leave-one-out ordering checks for the first post-burst state. "
        + ORDERING_NOTE
        + " Panel B covers the deep transition, escalation, and persistent-ownership order placebos. "
        + PLACEBO_NOTE,
    )


def glossary_rows() -> list[tuple[str, str, str]]:
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
    return [(tex(term), definition, tex(source)) for term, definition, source in entries]


def definitions_table() -> str:
    allowlist = [(product, aliases, "") for product, aliases in identity_rows()]
    return paneled_longtable(
        "Attribution allowlist and the glossary of load-bearing terms.",
        "tab:s-definitions",
        r"L{0.22\textwidth}L{0.57\textwidth}L{0.17\textwidth}",
        3,
        (
            (
                "Panel A. Attribution allowlist",
                ("Mapped product", "Exact GitHub login(s), matched case-insensitively", ""),
                allowlist,
            ),
            (
                "Panel B. Glossary of load-bearing terms",
                ("Term", "Definition in the code", "Where it is defined"),
                glossary_rows(),
            ),
        ),
        "Panel A is the exact public-account allowlist used for reviewer-product attribution; logins are matched case-insensitively. Only exact aliases are mapped. Similar names and unknown bots stay outside the six-product registry. Panel B is read from the analysis code: each definition is the rule the code applies, not an interpretation of it. The five states are mutually exclusive and cover every PR at every burst threshold. The seven roles are evaluated in the listed order, so the first matching branch wins. None of these labels reports intent, private activity, or whether a review point was resolved.",
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
    ("data", (release_table,)),
    ("identity", (definitions_table,)),
    ("cohorts", (cohort_table, specifications_table)),
    ("rq1", (burst_table, rq1_robustness_table)),
    ("rq2", (rq2_table,)),
    ("rq3", (addressed_edge_table, rq3_robustness_table)),
    ("external", (external_table,)),
    ("task_context", (task_context_table,)),
    ("quality", (quality_table,)),
    ("reproduction", (record_table,)),
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
