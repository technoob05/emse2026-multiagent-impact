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
    "tab:s-rq2",
    "tab:s-addressed-edge",
    "tab:s-sensitivity",
    "tab:s-specificity",
    "tab:s-task-context",
    "tab:s-external",
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


def release_table() -> str:
    inventory = read_csv(
        "outputs/tables/dataset_table_inventory.csv",
        ("table", "scope", "grain", "rows", "columns", "role"),
    )
    coverage = read_csv(
        "outputs/tables/dataset_join_coverage.csv",
        ("feature_group", "event_rows", "matched_pr_ids", "coverage_pct_of_aidev_pop", "orphan_pr_ids"),
    )
    inventory_rows: list[tuple[str, ...]] = []
    for item in inventory:
        inventory_rows.append(
            (
                breakable_identifier(item["table"]),
                tex(item["scope"].replace("AIDev-pop (>100 stars)", "Rich")),
                tex(item["grain"]),
                integer(item["rows"]),
                integer(item["columns"]),
                tex(item["role"]),
            )
        )
    coverage_rows: list[tuple[str, ...]] = []
    for item in coverage:
        coverage_rows.append(
            (
                tex(item["feature_group"]),
                tex("Rich"),
                tex("Linked rows"),
                integer(item["event_rows"]),
                integer(item["matched_pr_ids"]),
                tex(
                    f"{number(item['coverage_pct_of_aidev_pop']):.2f}% of the backbone; "
                    f"{integer(item['orphan_pr_ids'])} orphan PR identifiers"
                ),
            )
        )
    anchor = read_json("outputs/anchorability_coverage/summary.json")
    proxy = read_csv(
        "outputs/anchorability_coverage/coarse_unanchored_proxy.csv",
        ("trigger_channel", "trigger_prs", "coarse_proxy_rate"),
    )
    out_of_scope_proxy = one(proxy, trigger_channel="pr_comment")
    inline_proxy = one(proxy, trigger_channel="inline_review_comment")
    note = (
        "The rich layer contains repositories with more than 100 stars. Inventory row counts come from release metadata, so large content "
        "tables are not expanded in memory. Panel B describes the 361,296 rich-layer pull requests that form the backbone: coverage means that a "
        "pull request has at least one linked row, and inline comments resolve through their submitted-review identifier before joining to the "
        "pull request. Missing linked rows are not read as negative events, which is why each analysis declares its own denominator. "
        f"Panel C counts reviewer-side interaction events on the {integer(anchor['cohort']['trigger_prs'])} trigger PRs, split by the channel that "
        "carries them; only inline review comments store a machine-readable reply anchor, so only they can produce an exact addressed edge. Shares "
        "in the first four rows are of reviewer-side events and of trigger PRs; the last row's share is of inline events, and it gives the anchoring "
        "ceiling. A coarse unanchored proxy, any later comment by a different account inside the window, fires on "
        f"{percent(out_of_scope_proxy['coarse_proxy_rate'])}% of PR-level-comment triggers against {percent(inline_proxy['coarse_proxy_rate'])}% of "
        "inline triggers; it is reported to size the blind spot and is never used for estimation."
    )
    return paneled_longtable(
        "Release inventory, backbone coverage, and which review channels can carry a reply anchor.",
        "tab:s-dataset",
        r"L{0.20\textwidth}L{0.05\textwidth}L{0.13\textwidth}L{0.08\textwidth}L{0.09\textwidth}L{0.43\textwidth}",
        6,
        (
            (
                "Panel A. Release inventory",
                ("Release table", "Layer", "Unit", "Rows", "Fields", "Role"),
                inventory_rows,
            ),
            (
                "Panel B. Coverage of the 361,296-PR rich-layer backbone",
                ("Feature group", "Layer", "Unit", "Rows", "Matched PRs", "Coverage and join integrity"),
                coverage_rows,
            ),
            (
                "Panel C. Which review channels can carry a reply anchor at all",
                (
                    "Interaction channel",
                    "Anchor",
                    "Reviewer events",
                    "Share (\\%)",
                    "Trigger PRs",
                    "Share of triggers (\\%)",
                ),
                anchorability_rows(),
            ),
        ),
        note,
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
    "branch_movement_untyped": "Branch movement or untyped",
    "no_action_within_7d": "No later action in 7 days",
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

    burst = read_json("outputs/burst_threshold_selection/summary.json")
    agreement = read_csv(
        "outputs/burst_threshold_selection/agreement_with_five_minutes.csv",
        ("scheme", "state_agreement_with_fixed_five_minutes"),
    )
    others = [
        number(item["state_agreement_with_fixed_five_minutes"])
        for item in agreement
        if item["scheme"] != "fixed_5_minutes"
    ]
    if not others:
        raise ValueError("The agreement product has no comparison schemes")
    antimode = one(
        read_csv(
            "outputs/burst_threshold_selection/selected_cuts.csv",
            ("scope", "group", "rule", "cut_exists", "share_of_replicates_with_a_cut"),
        ),
        scope="global",
        group="all",
        rule="log_gap_kde_antimode",
    )
    if antimode["cut_exists"] != "False":
        raise ValueError("The antimode rule now selects a cut; the note would be wrong")
    hazard = burst["global_data_driven_cuts"]["log_hazard_change_point"]
    shape = burst["gap_distribution"]
    note = (
        "The denominator in Panel A is 8,608 PRs at every threshold. In Panel B the log gap density has a single dominant mode at "
        f"{compact_number(shape['kde_mode_minutes'][0], 2)} minutes with no interior antimode below "
        f"{compact_number(shape['burst_region_max_minutes'])} minutes, and the antimode rule finds a burst-region cut in only "
        f"{percent(antimode['share_of_replicates_with_a_cut'])}% of repository bootstrap replicates; the change-point rule always returns a value, "
        f"{compact_number(hazard['cut_minutes'], 2)} minutes globally, but it marks where responses start arriving rather than where a machine burst "
        f"ends. State agreement with the five-minute convention ranges from {percent(min(others))}% to {percent(max(others))}%. "
        + ORDERING_NOTE
        + " "
        + PLACEBO_NOTE
    )
    return paneled_longtable(
        "RQ1: first public state after each burst threshold, the burst-window convention, ordering diagnostics, and order placebos.",
        "tab:s-burst",
        r"L{0.13\textwidth}L{0.29\textwidth}L{0.08\textwidth}L{0.09\textwidth}L{0.16\textwidth}L{0.21\textwidth}",
        6,
        (
            (
                "Panel A. First public state after each rapid-burst threshold",
                ("Burst (min)", "First state", "PRs", "Share (\\%)", "Cluster 95\\% interval", "Median min"),
                rows,
            ),
            (
                "Panel B. First-owner split under nine burst-window schemes",
                (
                    "Burst-window scheme",
                    "Cut (min)",
                    "User (\\%)",
                    "Mapped (\\%)",
                    "User $-$ mapped (pp)",
                    "Repository-cluster 95\\% interval",
                ),
                burst_threshold_rows(),
            ),
            (
                "Panel C. Ordering diagnostics and leave-one-out checks",
                ("Check", "Quantity", "Burst (min)", "Full (\\%)", "Range or count", "Gate, shift, or diagnostic"),
                ordering_rows(),
            ),
            (
                "Panel D. Order placebos",
                ("Block", "Test or quantity", "At risk", "Observed (\\%)", "Null or difference (pp)", "95\\% interval"),
                rq1_placebo_rows(),
            ),
        ),
        note,
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
    "In Panel D the deep-transition shares use 924 mapped-first PRs; the same-product placebo uses 495 PRs with a later mapped-product event and preserves each PR's future product composition. Escalation rows compare the observed user-next share with a within-PR order permutation. Ownership rows condition on a visible next action, and their difference column is user-first minus mapped-first."
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
        "RQ2: the matched cross- versus same-product comparison, where its gap lives, and prior review history.",
        "tab:s-rq2",
        r"L{0.26\textwidth}L{0.09\textwidth}L{0.09\textwidth}L{0.11\textwidth}L{0.16\textwidth}L{0.25\textwidth}",
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
                "Panel B. Composition of the matched pairs and the gap inside each product pair",
                (
                    "Ordered product pair",
                    "Pairs",
                    "Repos",
                    "Cross (\\%)",
                    "Same (\\%)",
                    "Difference (pp) and repository-cluster 95\\% interval",
                ),
                matched_pair_rows(),
            ),
            (
                "Panel C. Strict prior same-repository review history",
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
            (
                "Panel D. Repository descriptors behind the RQ3 familiar-replier split",
                (
                    "Specification or pre-trigger descriptor",
                    "Familiar",
                    "Newcomer",
                    "Estimate or median gap",
                    "95\\% interval",
                    "Share explained or verdict",
                ),
                repository_moderator_rows(),
            ),
        ),
        "Panel A is the exact-author matched trigger comparison. "
        + BOUNDARY_NOTE
        + " "
        + heterogeneity_note()
        + " Panel C reports prior review history across user-account populations, and its median prior-PR count is taken among accounts with prior history. "
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
    routes = [
        ("48 h", route, prs, f"{merge} / {median}", difference, interval)
        for route, prs, merge, median, difference, interval in landmark_route_rows()
    ]
    return paneled_longtable(
        "RQ3: the exact-parent addressed edge, specificity controls, the four-state gradient, and the 48-hour ownership routes.",
        "tab:s-addressed-edge",
        r"L{0.09\textwidth}L{0.25\textwidth}L{0.11\textwidth}L{0.15\textwidth}L{0.14\textwidth}L{0.20\textwidth}",
        6,
        (
            (
                "Panel A. Addressed edge, specificity controls, and the four-state gradient",
                (
                    "Reply window",
                    "Specification or contrast",
                    "Compared PRs",
                    "Raw merge: compared / reference (\\%)",
                    "Adjusted difference (pp)",
                    "95\\% interval",
                ),
                rows,
            ),
            (
                "Panel B. Forty-eight-hour ownership routes and later integration",
                (
                    "Landmark",
                    "Route",
                    "PRs",
                    "Later merge (\\%) / median first action (h)",
                    "Adjusted difference (pp)",
                    "Repository-cluster 95\\% interval",
                ),
                routes,
            ),
        ),
        "The Panel A models use 1,067 inline-trigger PRs in 469 repositories that were open at hour 48 and had a complete 30-day horizon. Specificity rows compare 109 exact-edge PRs with 506 PRs that had public discussion but no exact edge. The gradient rows are one model over the full 1,067-PR cohort that places all four mutually exclusive post-trigger states against the no-visible-activity reference, with the same pre-trigger controls; its movement-only group holds 26 PRs, so that interval is wide and its point estimate is not a ranking. The active-discussion subset remains the primary specificity contrast because it does not compare an active PR with a silent one. This post-trigger discussion control is a structural falsification check, not a causal or semantic-resolution estimate. Panel B is the second pre-landmark signal, the mutually exclusive ownership route, on its own wider cohort. "
        + ROUTE_NOTE,
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

    # Balance holds at every reply window, so each control keeps one row: the
    # published 48-hour window, with the range the other three windows cover.
    for variable, label in BALANCE_VARIABLE_LABELS.items():
        by_window = {
            threshold: one(balance, threshold_hours=str(threshold), variable=variable)
            for threshold in (1, 6, 24, 48)
        }
        differences = [
            number(item["standardized_mean_difference"]) for item in by_window.values()
        ]
        primary = by_window[48]
        rows.append(
            (
                tex("Pre-trigger balance"),
                tex(label),
                f"{number(primary['standardized_mean_difference']):+.3f}",
                tex(f"{min(differences):+.3f} to {max(differences):+.3f} over 4 windows"),
                tex(
                    f"at 48 h: edge mean {number(primary['exposed_mean']):.3f}; "
                    f"no-edge mean {number(primary['unexposed_mean']):.3f}"
                ),
            )
        )
    quantiles = ("0.0", "0.05", "0.25", "0.5", "0.75", "0.95", "1.0")
    for group, label in (
        ("exact_edge", "Exact-edge PRs"),
        ("nonexact_discussion_only", "Non-exact-discussion PRs"),
    ):
        series = [
            f"{number(one(scores, group=group, quantile=quantile)['propensity_score']):.3f}"
            for quantile in quantiles
        ]
        rows.append(
            (
                tex("Propensity overlap"),
                tex(f"{label}: score at the 0, 5, 25, 50, 75, 95, and 100 percentiles (48 h)"),
                "--",
                "--",
                tex("; ".join(series)),
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

    # A negative control that behaves at every window collapses to its range;
    # the one that does not keeps a row per window, because that disagreement is
    # the reason the 48-hour window is primary.
    for key, label in control_labels.items():
        by_window = {
            threshold: one(negative, threshold_hours=str(threshold), negative_control_outcome=key)
            for threshold in (1, 6, 24, 48)
        }
        passes = {
            threshold: str(item["passes_null_expectation"]).strip().lower() == "true"
            for threshold, item in by_window.items()
        }
        if all(passes.values()):
            estimates = [number(item["estimate"]) for item in by_window.values()]
            lows = [number(item["ci_low"]) for item in by_window.values()]
            highs = [number(item["ci_high"]) for item in by_window.values()]
            rows.append(
                (
                    tex("Negative control"),
                    tex(f"{label}, all four reply windows"),
                    tex(f"{min(estimates):+.1f} to {max(estimates):+.1f}"),
                    tex(f"[{min(lows):+.1f}, {max(highs):+.1f}]"),
                    tex(f"{integer(by_window[48]['n_prs'])} PRs; every interval covers the null"),
                )
            )
            continue
        for threshold, item in by_window.items():
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
                            if passes[threshold]
                            else "interval excludes the null: residual pre-trigger confounding"
                        )
                    ),
                )
            )

    unconditional = {
        threshold: one(permutation, threshold_hours=str(threshold)) for threshold in (1, 6, 24, 48)
    }
    primary_permutation = unconditional[48]
    other_p = [
        number(item["permutation_p_value_two_sided"])
        for threshold, item in unconditional.items()
        if threshold != 48
    ]
    other_repos = [
        int(number(item["repositories_with_within_exposure_variation"]))
        for threshold, item in unconditional.items()
        if threshold != 48
    ]
    rows.append(
        (
            tex("Randomisation, unconditional"),
            tex("48 h reply window (published)"),
            pp(primary_permutation["observed_estimate"]),
            ci_pp(primary_permutation["permutation_quantile_025"], primary_permutation["permutation_quantile_975"]),
            tex(
                f"two-sided p = {number(primary_permutation['permutation_p_value_two_sided']):.3f} over "
                f"{integer(primary_permutation['permutations'])} within-repository permutations across "
                f"{integer(primary_permutation['repositories_with_within_exposure_variation'])} repositories"
            ),
        )
    )
    rows.append(
        (
            tex("Randomisation, unconditional"),
            tex("The other three reply windows"),
            "--",
            "--",
            tex(
                f"two-sided p = {min(other_p):.3f} to {max(other_p):.3f} across "
                f"{min(other_repos)} to {max(other_repos)} re-randomisable repositories"
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

    # The three control sets give the same answer, so they share one row.
    hazard_items = [one(hazard, specification=key) for key in hazard_labels]
    hazard_ratios = [number(item["hazard_odds_ratio"]) for item in hazard_items]
    hazard_low = min(number(item["or_ci_low"]) for item in hazard_items)
    hazard_high = max(number(item["or_ci_high"]) for item in hazard_items)
    hazard_p = max(number(item["p_value"]) for item in hazard_items)
    rows.append(
        (
            tex("Whole-population hazard"),
            tex("Time only; products and month; full pre-trigger controls"),
            tex(f"{min(hazard_ratios):.2f} to {max(hazard_ratios):.2f}"),
            tex(f"[{hazard_low:.2f}, {hazard_high:.2f}]"),
            tex(
                "odds ratio for merging in the next interval, over 3 control sets; "
                f"{integer(hazard_items[0]['prs'])} PRs, {integer(hazard_items[0]['person_period_rows'])} periods; "
                f"p at most {hazard_p:.2g}"
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
        r"L{0.10\textwidth}L{0.25\textwidth}L{0.08\textwidth}L{0.13\textwidth}L{0.42\textwidth}",
        (
            "Check",
            "Item",
            "Estimate",
            "95\\% interval or band",
            "Size and detail",
        ),
        rows,
        "Unless a row says otherwise, every check uses the 1,067-PR inline-trigger landmark cohort and the pre-trigger adjusted specification. A standardized mean difference is the group difference divided by the pooled standard deviation. E-values are computed on an approximate risk-ratio scale from the adjusted risk difference and the unexposed later-merge rate, and state the minimum association an unmeasured factor would need with both the exact edge and later merge, beyond the measured controls. The bracketed pair on the unconditional randomisation row is the 2.5th to 97.5th percentile of the permuted reference distribution, not a confidence interval, and that distribution is not centred on zero because 423 of 469 repositories contain no exposure variation; the conditional row, which is the one quoted in the article, uses only repositories containing both exposed and unexposed PRs and adds repository fixed effects, so its reference is centred. The whole-population row is an odds ratio from a pooled logistic model with interval indicators and repository-clustered standard errors, on follow-up split into eleven intervals with the edge entering as a time-varying covariate. Among the edge-class rows the fixed-effect row is the decisive one: the gap between a prior reviewer and a newcomer is largely a difference between repositories, not within them, so those rows describe where the signal sits and do not identify a mechanism. None of these checks identifies a causal effect.",
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
    gate_width = r"0.50\textwidth"
    gates = [
        (span(2, gate_width, name, first=True), status, value)
        for name, status, value in validation_gate_records()
    ]
    leakage = [
        (span(2, gate_width, label, first=True), count, role)
        for label, count, role in leakage_contract_rows()
    ]
    return paneled_longtable(
        "Cohort funnel, validation gates, and the column-level leakage contract.",
        "tab:s-cohort",
        r"L{0.36\textwidth}L{0.12\textwidth}L{0.13\textwidth}L{0.37\textwidth}",
        4,
        (
            (
                "Panel A. Participation-to-addressed-edge denominator funnel",
                ("Stage", "PRs", "Denominator", "Share (\\%)"),
                funnel_rows(),
            ),
            (
                "Panel B. Load-bearing validation gates",
                (span(2, gate_width, "Gate", first=True), "Status", "Observed"),
                gates,
            ),
            (
                "Panel C. Leakage contract on the landmark cohort columns",
                (span(2, gate_width, "Leakage tag stored with the cohort", first=True), "Columns", "Where the column may be used"),
                leakage,
            ),
        ),
        "Panel A is the denominator funnel. "
        + FUNNEL_NOTE
        + " In Panel B, PASS means that the frozen automated check met its declared contract; LIMIT identifies missing measurement coverage rather"
        " than a failed computation. Panel C is the column-by-column form of the pre-trigger-only claim: every column of the derived landmark cohort"
        " carries a leakage tag, and the tag decides where the column may enter a model. It records where a value can be observed, not whether it is"
        " a good measure of the thing it is named after. The public artifact carries the full column dictionary with one row per column.",
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


def validation_gate_records() -> list[tuple[str, str, str]]:
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
    return [(tex(name), tex(status), tex(value)) for name, status, value in checks]


LEAKAGE_ROLES = {
    "at_or_before_trigger": "The primary specification draws only on these.",
    "posttrigger_by_48h": "Used only by the secondary route decomposition and by the exposure itself.",
    "outcome": "Read only after hour 48; never an input.",
}


def leakage_contract_rows() -> list[tuple[str, ...]]:
    """Summarise the stored leakage tag by class rather than column by column.

    The per-column dictionary is a repository artifact: it names internal column
    identifiers that mean nothing without a checkout. What a reader needs is the
    contract itself, which is one row per tag.
    """
    schema = read_json("outputs/addressed_edge_landmark/schema.json")
    columns = schema.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("The landmark schema has no column list")
    counts: dict[str, int] = defaultdict(int)
    for entry in columns:
        availability = entry["available_when"]
        if availability not in AVAILABILITY_LABELS:
            raise ValueError(f"Unknown leakage tag: {availability}")
        counts[availability] += 1
    if sum(counts.values()) != len(columns):
        raise ValueError("The leakage tag counts do not cover every column")
    rows = [
        (
            tex(AVAILABILITY_LABELS[tag]),
            f"{counts[tag]} of {len(columns)}",
            tex(LEAKAGE_ROLES[tag]),
        )
        for tag in ("at_or_before_trigger", "posttrigger_by_48h", "outcome")
        if counts[tag]
    ]
    return rows


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
    "log1p_trigger_age_hours": "Log trigger age (h)",
    "log1p_pre_events": "Log pre-trigger events",
    "pre_user_events": "Pre-trigger user events",
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

# A published Online Resource cannot ask its reader to look up a column name, so
# every model term is rendered as the quantity it stands for. The gate fails
# closed: a term the map does not know stops the build rather than reaching the
# page as a raw identifier.
TERM_LABELS = {
    "merged_from_48h_to_30d": "later merge, hour 48 to day 30",
    "prior_different_pr_reviewer": "prior review in this repository on another PR",
    "exact_parent_reply_by_1h": "exact reply within 1 h",
    "exact_parent_reply_by_6h": "exact reply within 6 h",
    "exact_parent_reply_by_24h": "exact reply within 24 h",
    "exact_parent_reply_by_48h": "exact reply within 48 h",
    "exact_edge_by_1h": "exact edge within 1 h, against other visible discussion",
    "exact_edge_by_6h": "exact edge within 6 h, against other visible discussion",
    "exact_edge_by_24h": "exact edge within 24 h, against other visible discussion",
    "exact_edge_by_48h": "exact edge within 48 h, against other visible discussion",
    "exact_user_edge_by_48h": "exact user-written edge within 48 h, against other user discussion",
    "specificity_group_48h": "48-hour response state",
    "C(specificity_group_48h)": "48-hour response state",
    "ownership_route_48h": "48-hour ownership route",
    "other_user": "the bridge is not the PR author",
    "is_first": "first responder in the window",
    "is_author": "the responder is the PR author",
    "C(author_agent)": "author product",
    "C(trigger_reviewer_agent)": "reviewer product",
    "C(trigger_month)": "calendar month",
    "C(trigger_source)": "trigger channel",
    "log1p_trigger_age_hours": "log trigger age",
    "log1p_pre_events": "log pre-trigger events",
    "pre_user_events": "pre-trigger user events",
    "pre_bot_events": "pre-trigger bot events",
    "pre_decisive_reviews": "pre-trigger decisive reviews",
    "pre_force_pushes": "pre-trigger branch movements",
}

# The nine terms every outcome model shares. Naming the block once keeps each
# row to the part that actually differs between specifications.
PRETRIGGER_CONTROL_SET = (
    "C(author_agent)",
    "C(trigger_reviewer_agent)",
    "C(trigger_month)",
    "log1p_trigger_age_hours",
    "log1p_pre_events",
    "pre_user_events",
    "pre_bot_events",
    "pre_decisive_reviews",
    "pre_force_pushes",
)
CONTROL_SET_NAME = "the pre-trigger control set"


def term_label(term: str) -> str:
    term = term.strip()
    treatment = re.fullmatch(r"C\((\w+),\s*Treatment\('([^']+)'\)\)", term)
    if treatment:
        base = TERM_LABELS.get(f"C({treatment.group(1)})") or TERM_LABELS.get(treatment.group(1))
        if base is None:
            raise ValueError(f"Unmapped model term: {term!r}")
        reference = treatment.group(2).replace("_", " ")
        return f"{base} (reference: {reference})"
    if term not in TERM_LABELS:
        raise ValueError(f"Unmapped model term: {term!r}")
    return TERM_LABELS[term]


def readable_adjustment(formula: str) -> str:
    """Render the right-hand side of a stored formula as readable terms."""
    if "~" not in formula:
        raise ValueError(f"Formula has no response term: {formula!r}")
    right = formula.split("~", 1)[1]
    terms = [part.strip() for part in right.split(" + ") if part.strip()]
    control_set = list(PRETRIGGER_CONTROL_SET)
    if all(term in terms for term in control_set):
        labels = [CONTROL_SET_NAME]
        remaining = [term for term in terms if term not in control_set]
    else:
        labels = []
        remaining = terms
    labels.extend(term_label(term) for term in remaining[1:])
    if not labels:
        return tex("exposure only; no adjustment")
    return tex("exposure plus " + ", ".join(labels))


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
            tex(term_label("merged_from_48h_to_30d")),
            tex(term_label(exposure)),
            f"{integer(item['n_prs'])} / {integer(item['repositories'])}",
            readable_adjustment(item["formula"]),
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
                tex(term_label("merged_from_48h_to_30d")),
                tex(term_label("ownership_route_48h") + " (reference: automation, no user event)"),
                f"{integer(item['n_prs'])} / {integer(item['repositories'])}",
                readable_adjustment(formula),
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
                tex(term_label("prior_different_pr_reviewer")),
                tex(term_label(term)),
                f"{integer(item['n'])} / {integer(item['repositories'])}",
                readable_adjustment(formula),
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
    resampling: list[tuple[str, ...]] = []
    for analysis, unit, draws, seed, method in records:
        resampling.append(
            (
                tex(analysis),
                tex(unit),
                tex("no resampling" if draws == "--" else draws),
                tex("--" if seed == "--" else seed),
                tex(method),
            )
        )

    return paneled_longtable(
        "Named estimation specifications and the resampling settings behind every reported interval.",
        "tab:s-specifications",
        r"L{0.17\textwidth}L{0.15\textwidth}L{0.13\textwidth}L{0.23\textwidth}L{0.30\textwidth}",
        5,
        (
            (
                "Panel A. Named estimation specifications",
                ("Analysis", "Outcome", "Exposure term", "PRs / repos", "Adjustment"),
                rows,
            ),
            (
                "Panel B. Resampling settings behind every reported interval",
                ("Analysis", "Resampling unit", "Draws", "Seed", "Interval method"),
                resampling,
            ),
        ),
        "Every model in Panel A is a linear probability model fitted by ordinary least squares, with standard errors clustered on the repository; the two"
        " prior-history rows add a small-cluster correction. Adjustment terms are read back from the formula stored with each analysis product, except"
        " the two route rows and the two prior-history rows, whose formulas are read from the analysis code. "
        f"{CONTROL_SET_NAME.capitalize()} is author product, reviewer product, calendar month, log trigger age, log pre-trigger events, and pre-trigger"
        " user, bot, decisive-review, and branch-movement counts. Reply-window variants at 1, 6, and 24 hours refit the same specification with that"
        " window's exposure term. In Panel B the draw counts are not uniform, so they are listed rather than summarised; every seed derives from one"
        " fixed value, with fixed offsets so that separate quantities inside one analysis do not reuse a single draw sequence. A percentile band is the"
        " 2.5th and 97.5th percentile of the draw distribution. The last row records that regression intervals come from a clustered normal"
        " approximation, which is why the exact-edge estimate is also checked by permutation. A specification describes the fit; it does not claim that"
        " the fit identifies an effect.",
    )


AVAILABILITY_LABELS = {
    "at_or_before_trigger": "At or before the trigger",
    "posttrigger_by_48h": "After the trigger, by hour 48",
    "outcome": "Outcome window, after hour 48",
}


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
    "run_anchorability_coverage.py": ("Which review channels carry a reply anchor, and the share of triggers in scope", "outputs/anchorability_coverage/trigger_channel_composition.csv"),
    "run_burst_threshold_selection.py": ("Data-driven burst cuts, per-product cuts, RQ1 owner split under nine schemes", "outputs/burst_threshold_selection/owner_split_sensitivity.csv"),
    "run_pseudo_edge_negative_control.py": ("Off-target, permuted-anchor, and time-shifted placebo exposures", "outputs/pseudo_edge_control/contrasts.csv"),
    "run_user_account_automation_audit.py": ("Machine-likeness heuristics on edge-writing accounts and the re-estimated contrast", "outputs/user_account_automation/heuristic_incidence.csv"),
    "run_addressed_edge_reply_content_audit.py": ("Reply-content classification of every addressed edge and the contrast by category", "outputs/user_account_automation/reply_content_category_counts.csv"),
    "run_heterogeneity_audit.py": ("Matched-pair composition, per-product-pair gaps, repository moderators", "outputs/heterogeneity_audit/matched_pair_by_product_pair.csv"),
    "run_worked_example.py": ("One traced pull request, event by event, behind the measurement figure", "outputs/worked_example/timeline.csv"),
    "run_confounder_benchmarks.py": ("The measured controls placed on the same scale as a hypothetical hidden cause", "outputs/confounder_benchmarks/measured_factor_positions.csv"),
    "prepare_review_collision_audit.py": ("Blinded structural same-locus coder packets", "outputs/review_collision/product_pair_concentration.csv"),
    "run_collision_descriptive_extension.py": ("Descriptive timing and concentration for the same-locus population", "outputs/novelty_collision_extension/timing_distribution.csv"),
    "generate_technical_appendix_tables.py": ("Every table in this appendix", ""),
    "validate_response_ownership_outputs.py": ("Re-checks the ownership products against their frozen contracts", ""),
    "validate_coordination_extension_outputs.py": ("Re-checks the topology and landmark products", ""),
    "visualize_manuscript_figures.py": ("The six article figures and the two appendix figures", ""),
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
    claim_width = r"0.35\textwidth"
    dispositions = [
        (span(2, claim_width, claim, first=True), status, reason)
        for claim, status, reason in disposition_rows()
    ]
    return paneled_longtable(
        "Ordered reproduction contract and the disposition of every experiment.",
        "tab:s-record",
        r"L{0.04\textwidth}L{0.29\textwidth}L{0.09\textwidth}L{0.54\textwidth}",
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
    unit_labels = {"repository": "one repository", "product_pair": "one ordered product pair"}
    thresholds = (0, 1, 5, 10, 30)
    rows: list[tuple[str, ...]] = []

    # Every threshold agrees, so the five tie diagnostics collapse to their range
    # and the one fact that could change an assigned state: a mixed-state tie.
    tie_items = [one(diagnostics, burst_threshold_minutes=str(threshold)) for threshold in thresholds]
    tie_counts = [int(number(item["first_timestamp_tie_prs"])) for item in tie_items]
    mixed_total = sum(int(number(item["mixed_state_tie_prs"])) for item in tie_items)
    mixed_thresholds = [
        threshold
        for threshold, item in zip(thresholds, tie_items)
        if int(number(item["mixed_state_tie_prs"]))
    ]
    largest_group = max(int(number(item["maximum_events_at_first_timestamp"])) for item in tie_items)
    rows.append(
        (
            tex("Tie diagnostic"),
            tex("Tied first timestamps among PRs with a post-burst action"),
            tex("all 5"),
            "--",
            tex(f"{min(tie_counts):,} to {max(tie_counts):,} PRs"),
            tex(
                f"{mixed_total} mixed-state tie in total"
                + (f", at {mixed_thresholds[0]} min" if len(mixed_thresholds) == 1 else "")
                + f"; largest tie group {largest_group}"
            ),
        )
    )

    # The gate holds in every exclusion at every threshold, so only the published
    # five-minute threshold keeps its own row and the rest collapse to a range.
    for unit in ("repository", "product_pair"):
        items = {
            threshold: one(robustness, burst_threshold_minutes=str(threshold), exclusion_unit=unit)
            for threshold in thresholds
        }
        for item in items.values():
            gates_hold = (
                str(item["user_exceeds_mapped_in_every_exclusion"]).strip().lower() == "true"
                and str(item["no_action_is_largest_in_every_exclusion"]).strip().lower() == "true"
            )
            if not gates_hold:
                raise ValueError("A leave-one-out ordering gate now fails; the collapsed row would be wrong")
        exclusions = int(number(items[5]["exclusions"]))
        rows.append(
            (
                tex("Leave-one-out ordering gate"),
                tex(f"User minus mapped product, dropping {unit_labels[unit]}"),
                "5",
                "--",
                tex(
                    f"{number(items[5]['minimum_user_minus_mapped_percentage_points']):.1f} to "
                    f"{number(items[5]['maximum_user_minus_mapped_percentage_points']):.1f} pp"
                ),
                tex(f"both gates hold in all {exclusions:,} exclusions"),
            )
        )
        low = min(number(items[threshold]["minimum_user_minus_mapped_percentage_points"]) for threshold in thresholds if threshold != 5)
        high = max(number(items[threshold]["maximum_user_minus_mapped_percentage_points"]) for threshold in thresholds if threshold != 5)
        rows.append(
            (
                tex("Leave-one-out ordering gate"),
                tex(f"The same gate at the other four thresholds, dropping {unit_labels[unit]}"),
                tex("0, 1, 10, 30"),
                "--",
                tex(f"{low:.1f} to {high:.1f} pp"),
                tex("both gates hold in every exclusion at every threshold"),
            )
        )

    for state in (
        "user_account",
        "mapped_product",
        "other_bot",
        "branch_movement_untyped",
        "no_action_within_7d",
    ):
        by_unit = {
            unit: one(
                ranges,
                burst_threshold_minutes="5",
                exclusion_unit=unit,
                first_post_burst_state=state,
            )
            for unit in ("repository", "product_pair")
        }
        repository, product_pair = by_unit["repository"], by_unit["product_pair"]
        rows.append(
            (
                tex("Leave-one-out share range"),
                tex(f"{STATE_LABELS[state]}: dropping one repository, then one product pair"),
                "5",
                percent(repository["full_share"]),
                tex(
                    f"{percent(repository['minimum_loo_share'])} to {percent(repository['maximum_loo_share'])}; "
                    f"{percent(product_pair['minimum_loo_share'])} to {percent(product_pair['maximum_loo_share'])}"
                ),
                tex(
                    f"largest shift {number(repository['maximum_absolute_shift_percentage_points']):.2f} pp; "
                    f"{number(product_pair['maximum_absolute_shift_percentage_points']):.2f} pp"
                ),
            )
        )
    return rows


ORDERING_NOTE = (
    "In Panel C the two gates checked in every exclusion are that the user-account share stays above the mapped-product share and that no later action within seven days stays the largest state. Because both hold everywhere, the four non-published thresholds are collapsed to their range. The share-range rows report each state at the five-minute threshold, first for repository exclusions and then for product-pair exclusions. These checks show that the ordering is not carried by one repository or one product pair; they do not remove selection into the cohort."
)


def glossary_rows() -> list[tuple[str, str]]:
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

    # Only terms whose exact rule the article does not already state are kept.
    # The five actor states and the seven response roles are each one row, in
    # priority order, rather than one row per branch of the same classifier.
    entries: list[tuple[str, str]] = [
        (
            "Decisive review",
            "A submitted review whose state is APPROVED or CHANGES\\_REQUESTED. Commented and pending reviews are not decisive.",
        ),
        (
            "Branch movement",
            "A force-push event on the PR branch. It is visible movement of the branch, not a verified repair.",
        ),
        (
            "Untyped activity",
            "A post-trigger event row that is not a user account, a mapped product, or another bot. It is the residual class and is always reported together with branch movement.",
        ),
        (
            "The five first-state classes, in priority order",
            "(1) user account, the event's GitHub user type is User, which takes precedence over product mapping; "
            "(2) mapped product, a non-User account on the six-product allowlist; "
            "(3) other bot, a Bot account not on the allowlist; "
            "(4) branch movement or untyped activity, every remaining event row; "
            "(5) no later action within seven days. The classes are mutually exclusive and cover every PR at every burst threshold.",
        ),
        (
            "The seven response actor roles, in evaluation order",
            "(1) the PR author's own user account, a User whose login equals the author's; "
            "(2) the PR author's product; (3) the triggering product; (4) a different mapped product; "
            "(5) an unmapped bot; (6) another user account; (7) unknown actor, an event with no usable user type, kept so the roles stay exhaustive. "
            "The first matching branch wins.",
        ),
        (
            "Automation episode",
            "A run of post-burst events on one PR in which each event follows the previous one by no more than the gap parameter; a larger gap starts a new episode. The primary gap is five minutes, and the first five minutes after the trigger are excluded before episodes are built.",
        ),
        (
            "Episode state",
            "The highest-priority state inside the episode, using the same priority order as the tie rule. At the five-minute gap, "
            + f"{integer(primary['mixed_state_episodes'])} of {integer(primary['episodes'])} episodes mix states.",
        ),
    ]
    return [(tex(term), definition) for term, definition in entries]


def definitions_table() -> str:
    return paneled_longtable(
        "Attribution allowlist and the rules behind the load-bearing labels.",
        "tab:s-definitions",
        r"L{0.27\textwidth}L{0.71\textwidth}",
        2,
        (
            (
                "Panel A. Attribution allowlist",
                ("Mapped product", "Exact GitHub login(s), matched case-insensitively"),
                identity_rows(),
            ),
            (
                "Panel B. Terms whose exact rule the article does not state",
                ("Term", "The rule the analysis code applies"),
                glossary_rows(),
            ),
        ),
        "Panel A is the exact public-account allowlist used for reviewer-product attribution. Only exact aliases are mapped; similar names and unknown bots stay outside the six-product registry. Panel B is read back from the analysis code, so each entry is the rule the code applies rather than an interpretation of it. Terms the article already defines are not repeated here. None of these labels reports intent, private activity, or whether a review point was resolved.",
    )


def pp_value(value: object, digits: int = 1, signed: bool = True) -> str:
    """Format a quantity that the analysis product already stores in points."""
    amount = number(value)
    return f"{amount:+.{digits}f}" if signed else f"{amount:.{digits}f}"


def ci_pp_value(low: object, high: object, digits: int = 1) -> str:
    return f"[{pp_value(low, digits)}, {pp_value(high, digits)}]"


def comparison_math(value: object) -> str:
    """Escape for TeX, then set inequality and tolerance signs in math mode."""
    return (
        tex(value)
        .replace(">=", r"$\ge$")
        .replace("<=", r"$\le$")
        .replace("+/-", r"$\pm$")
    )


def p_text(value: object) -> str:
    amount = number(value)
    return "p < 0.001" if amount < 0.001 else f"p = {amount:.3f}"


def anchorability_rows() -> list[tuple[str, ...]]:
    summary = read_json("outputs/anchorability_coverage/summary.json")
    volume = read_csv(
        "outputs/anchorability_coverage/channel_interaction_volume.csv",
        ("channel", "channel_label", "carries_reply_anchor", "reviewer_side_events", "share_of_reviewer_side_events"),
    )
    triggers = read_csv(
        "outputs/anchorability_coverage/trigger_channel_composition.csv",
        ("trigger_channel", "in_scope_for_the_addressed_edge", "trigger_prs", "share_of_trigger_prs"),
    )
    split = read_csv(
        "outputs/anchorability_coverage/inline_root_reply_split.csv",
        ("position", "can_receive_an_exact_parent_edge", "inline_events", "share_of_inline_events"),
    )
    rows: list[tuple[str, ...]] = []
    for item in volume:
        trigger = one(triggers, trigger_channel=item["channel"])
        if item["carries_reply_anchor"] != trigger["in_scope_for_the_addressed_edge"]:
            raise ValueError(f"Anchor flag disagrees with trigger scope for {item['channel']}")
        # The release table name is already given in the inventory panel, so the
        # parenthetical is dropped rather than repeated as prose.
        label = re.sub(r"\s*\([^)]*\)\s*$", "", item["channel_label"])
        rows.append(
            (
                tex(label),
                "Yes" if item["carries_reply_anchor"] == "True" else "No",
                integer(item["reviewer_side_events"]),
                percent(item["share_of_reviewer_side_events"]),
                integer(trigger["trigger_prs"]),
                percent(trigger["share_of_trigger_prs"]),
            )
        )
    reviewer = summary["reviewer_side_interaction_volume"]
    composition = summary["trigger_channel_composition"]
    rows.append(
        (
            tex("All channels that carry no reply anchor"),
            "No",
            integer(reviewer["non_anchorable_events"]),
            percent(reviewer["non_anchorable_share_of_reviewer_side_events"]),
            integer(composition["out_of_scope_trigger_prs"]),
            percent(composition["out_of_scope_trigger_share"]),
        )
    )
    root = one(split, position="thread_root")
    rows.append(
        (
            tex("Inline thread roots, the only events an exact reply can name"),
            "Yes",
            integer(root["inline_events"]),
            percent(root["share_of_inline_events"]),
            "--",
            "--",
        )
    )
    return rows


BURST_SCHEME_LABELS = {
    "fixed_0_minutes": "Fixed convention, no burst excluded",
    "fixed_1_minutes": "Fixed convention",
    "fixed_5_minutes": "Fixed convention (published)",
    "fixed_10_minutes": "Fixed convention",
    "fixed_30_minutes": "Fixed convention",
    "global_log_hazard_change_point": "Data-driven global log-hazard change point",
    "global_log_hazard_change_point_burst_region": "Same rule, search capped at 60 minutes",
    "product_specific_log_hazard_change_point": "Per-product log-hazard change point",
    "product_specific_log_hazard_change_point_burst_region": "Per-product rule, search capped at 60 minutes",
}


def burst_threshold_rows() -> list[tuple[str, ...]]:
    summary = read_json("outputs/burst_threshold_selection/summary.json")
    applied = summary["product_specific_cuts_applied"]
    data = read_csv(
        "outputs/burst_threshold_selection/owner_split_sensitivity.csv",
        (
            "scheme",
            "scheme_kind",
            "threshold_minutes",
            "user_share_all_prs",
            "mapped_share_all_prs",
            "user_minus_mapped_percentage_points_all_prs",
            "user_minus_mapped_ci_low_pp_all_prs",
            "user_minus_mapped_ci_high_pp_all_prs",
            "user_exceeds_mapped_interval_excludes_zero",
        ),
    )
    rows: list[tuple[str, ...]] = []
    for item in data:
        scheme = item["scheme"]
        if scheme not in BURST_SCHEME_LABELS:
            raise ValueError(f"Unknown burst threshold scheme: {scheme}")
        if item["scheme_kind"] == "product_specific":
            rule = scheme.replace("product_specific_", "")
            cuts = applied.get(rule)
            if not isinstance(cuts, dict) or not cuts:
                raise ValueError(f"No applied per-product cuts recorded for {rule}")
            values = sorted(number(value) for value in cuts.values())
            cut = f"{compact_number(values[0])}--{compact_number(values[-1])}"
        else:
            cut = compact_number(item["threshold_minutes"])
        if item["user_exceeds_mapped_interval_excludes_zero"] != "True":
            raise ValueError(f"Scheme {scheme} no longer excludes zero; the note would be wrong")
        rows.append(
            (
                tex(BURST_SCHEME_LABELS[scheme]),
                cut,
                percent(item["user_share_all_prs"]),
                percent(item["mapped_share_all_prs"]),
                pp_value(item["user_minus_mapped_percentage_points_all_prs"]),
                ci_pp_value(
                    item["user_minus_mapped_ci_low_pp_all_prs"],
                    item["user_minus_mapped_ci_high_pp_all_prs"],
                ),
            )
        )
    return rows


PSEUDO_EDGE_LABELS = {
    "addressed_edge_observed": "Observed addressed edge (published exposure)",
    "off_target_reply": "Placebo: exact reply anchored to a different inline comment",
    "any_inline_reply_diagnostic": "Diagnostic: any inline reply inside the window",
}


def pseudo_edge_rows() -> list[tuple[str, ...]]:
    summary = read_json("outputs/pseudo_edge_control/summary.json")
    models = read_csv(
        "outputs/pseudo_edge_control/observed_exposure_models.csv",
        ("exposure", "prs", "exposed_prs", "estimate_pp", "ci_low", "ci_high", "p_value"),
    )
    nulls = read_csv(
        "outputs/pseudo_edge_control/permutation_null_summary.csv",
        (
            "control",
            "null_mean_pp",
            "null_quantile_025_pp",
            "null_quantile_975_pp",
            "observed_percentile_in_null",
            "p_value_two_sided",
            "null_centred_near_zero",
        ),
    )

    def model_row(exposure: str) -> tuple[str, ...]:
        item = one(models, exposure=exposure)
        return (
            tex(PSEUDO_EDGE_LABELS[exposure]),
            integer(item["prs"]),
            integer(item["exposed_prs"]),
            pp_value(item["estimate_pp"]),
            ci_pp_value(item["ci_low"], item["ci_high"]),
            tex(p_text(item["p_value"])),
        )

    def null_row(control: str, label: str, exposed: str) -> tuple[str, ...]:
        item = one(nulls, control=control)
        return (
            tex(label),
            integer(summary["cohort_prs"]),
            exposed,
            pp_value(item["null_mean_pp"]),
            ci_pp_value(item["null_quantile_025_pp"], item["null_quantile_975_pp"]),
            tex(
                f"observed at percentile {number(item['observed_percentile_in_null']):.2f}, "
                + p_text(item["p_value_two_sided"])
            ),
        )

    joint = summary["joint_on_vs_off_target"]
    rows = [
        model_row("addressed_edge_observed"),
        model_row("off_target_reply"),
        (
            tex("Joint model: addressed edge minus off-target reply"),
            integer(joint["prs"]),
            "--",
            pp_value(joint["difference_pp"]),
            ci_pp_value(joint["difference_ci_low"], joint["difference_ci_high"]),
            tex(p_text(joint["difference_p_value"])),
        ),
        null_row(
            "permuted_anchor[calendar_month]",
            "Placebo: permuted anchor, calendar month, fully permutable",
            integer(summary["permuted_anchor_null_reference"]["exposed_prs_per_draw"]),
        ),
        null_row(
            "permuted_anchor[repository_month]",
            "Placebo: permuted anchor, repository by month, degenerate support",
            integer(summary["permuted_anchor_null_primary"]["exposed_prs_per_draw"]),
        ),
        null_row(
            "time_shifted_edge",
            "Placebo: time-shifted edge, drawn independently of the PR's history",
            compact_number(summary["time_shifted_null"]["mean_exposed_prs_per_draw"]),
        ),
        model_row("any_inline_reply_diagnostic"),
    ]
    return rows


REPLY_CONTENT_LABELS = {
    "platform_generated": "Platform button text written on the person's behalf",
    "agent_invocation": "Agent invocation: the point is handed to a machine",
    "acknowledgement_only": "Acknowledgement only, below the twelve-word floor",
    "substantive_response": "Substantive engineering prose",
}


def reply_content_rows() -> list[tuple[str, ...]]:
    summary = read_json("outputs/user_account_automation/reply_content_summary.json")
    counts = read_csv(
        "outputs/user_account_automation/reply_content_category_counts.csv",
        ("scope", "labelling", "category", "edges", "edges_total", "share"),
    )
    contrasts = read_csv(
        "outputs/user_account_automation/addressed_edge_contrast_by_reply_content.csv",
        ("contrast", "exposure", "exposed_prs", "estimate", "ci_low", "ci_high", "dropped_prs"),
    )
    total = number(summary["user_written_edges"])
    rows: list[tuple[str, ...]] = []
    for category, label in REPLY_CONTENT_LABELS.items():
        rule = one(counts, scope="user_written_edges", labelling="rule_category", category=category)
        read = one(counts, scope="user_written_edges", labelling="human_category", category=category)
        if category == "substantive_response":
            model = one(
                contrasts,
                contrast="substantive user-written edge; other exposed PRs counted as unexposed",
            )
            estimate = pp(model["estimate"])
            interval = ci_pp(model["ci_low"], model["ci_high"])
        else:
            estimate = "--"
            interval = "--"
        rows.append(
            (
                tex(label),
                integer(rule["edges"]),
                percent(rule["share"]),
                integer(read["edges"]),
                estimate,
                interval,
            )
        )
    routing = one(
        contrasts,
        contrast="routing edge (agent invocation or platform text); other exposed PRs counted as unexposed",
    )
    rows.append(
        (
            tex("Routing edge: the first two categories combined"),
            integer(summary["routing_edges_user_written"]),
            percent(summary["routing_share_user_written"]),
            "--",
            pp(routing["estimate"]),
            ci_pp(routing["ci_low"], routing["ci_high"]),
        )
    )
    published = one(contrasts, contrast="any exact addressed edge (published estimate)")
    rows.append(
        (
            tex("Any addressed edge, the published exposure"),
            integer(total),
            percent(1.0),
            integer(total),
            pp(published["estimate"]),
            ci_pp(published["ci_low"], published["ci_high"]),
        )
    )
    return rows


def specificity_table() -> str:
    summary = read_json("outputs/pseudo_edge_control/summary.json")
    content = read_json("outputs/user_account_automation/reply_content_summary.json")
    verdict = str(summary["specificity_verdict"])
    if "NOT_SPECIFIC" not in verdict:
        raise ValueError("The frozen specificity verdict changed; the note would be wrong")
    agreement = content["rule_versus_reading"]
    note = (
        "Panel A is one row per exposure or per placebo null, all on the same inline-trigger landmark cohort and the same pre-trigger control set. "
        "Rows one to three are clustered linear-probability estimates; rows four to six are null distributions over 2,000 draws, so their bracketed pair is the "
        "2.5 to 97.5 percentile of the null rather than a confidence interval. The permuted-anchor null is centred near the observed estimate "
        f"({pp_value(summary['permuted_anchor_null_reference']['null_mean_pp'])} pp against an observed {pp_value(summary['addressed_edge']['estimate_pp'])} pp), "
        f"and the frozen verdict recorded with the analysis is {verdict}. "
        f"Panel B shares are of the {integer(content['user_written_edges'])} user-written edges among the {integer(content['all_edges'])} exposure events; the rule "
        f"and a full hand reading of all {integer(agreement['edges_hand_read'])} texts disagree on {integer(agreement['disagreements'])} rows "
        f"({percent(agreement['disagreement_rate'])}%), always in the conservative direction. Its subgroup contrasts are underpowered by construction and are "
        "description, not a causal decomposition. Every classified reply and every placebo draw is in the public artifact. "
        + actors_note()
    )
    return paneled_longtable(
        "Placebo exposures, what the reply says, and whether a person wrote it.",
        "tab:s-specificity",
        r"L{0.26\textwidth}L{0.07\textwidth}L{0.09\textwidth}L{0.11\textwidth}L{0.15\textwidth}L{0.28\textwidth}",
        6,
        (
            (
                "Panel A. Placebo exposures against the observed addressed edge",
                (
                    "Exposure or placebo null",
                    "PRs",
                    "Exposed",
                    "Estimate or null mean (pp)",
                    "95\\% interval or null 2.5--97.5\\%",
                    "$p$ or position in the null",
                ),
                pseudo_edge_rows(),
            ),
            (
                "Panel B. What the addressed-edge reply actually says",
                (
                    "Reply category",
                    "Edges (rule)",
                    "Share (\\%)",
                    "Edges (hand read)",
                    "Contrast (pp)",
                    "Repository-cluster 95\\% interval",
                ),
                reply_content_rows(),
            ),
            (
                "Panel C. Machine-likeness heuristics on the edge-writing accounts",
                (
                    "Heuristic",
                    "Accounts",
                    "Account share (\\%)",
                    "Edge events",
                    "Event share (\\%)",
                    "Pre-registered statistic and threshold",
                ),
                automation_flag_rows(),
            ),
            (
                "Panel D. The later-merge contrast after dropping flagged accounts",
                (
                    "Cohort",
                    "PRs",
                    "Exposed",
                    "Exposed merge (\\%)",
                    "Estimate (pp)",
                    "Repository-cluster 95\\% interval",
                ),
                automation_contrast_rows(),
            ),
        ),
        note,
    )


AUTOMATION_FLAG_LABELS = {
    "flag_template": "Template repetition",
    "flag_timing": "Regular inter-comment timing",
    "flag_clock": "No diurnal dip in the clock",
    "flag_volume": "Sustained comments per active day",
    "flag_any": "Any single heuristic",
    "flag_combined": "At least two heuristics (pre-registered rule)",
}

# The stored statistic names are column identifiers, which mean nothing without a
# repository checkout, so each is stated as the quantity it measures.
AUTOMATION_STATISTIC_LABELS = {
    "flag_template": "share of the account's comments that repeat an already-seen normalised text",
    "flag_timing": "coefficient of variation of inter-comment gaps, or the share of gaps in a narrow band around the median",
    "flag_clock": "number of occupied UTC hours, and the quietest hour's share of the uniform expectation",
    "flag_volume": "comments per active day",
}


def automation_flag_rows() -> list[tuple[str, ...]]:
    incidence = read_csv(
        "outputs/user_account_automation/heuristic_incidence.csv",
        ("flag", "accounts", "account_share", "edge_events", "edge_event_share"),
    )
    thresholds = read_csv(
        "outputs/user_account_automation/preregistered_thresholds.csv",
        ("heuristic", "statistic", "threshold"),
    )
    rows: list[tuple[str, ...]] = []
    for item in incidence:
        flag = item["flag"]
        if flag not in AUTOMATION_FLAG_LABELS:
            raise ValueError(f"Unknown machine-likeness heuristic: {flag}")
        matches = [entry for entry in thresholds if entry["heuristic"] == flag]
        if len(matches) > 1:
            raise ValueError(f"Duplicate threshold definition for {flag}")
        if matches:
            statistic = AUTOMATION_STATISTIC_LABELS.get(flag)
            if statistic is None:
                raise ValueError(f"No readable statistic name for {flag}")
            rule = comparison_math(f"{statistic} ({matches[0]['threshold']})")
        else:
            rule = "--"
        rows.append(
            (
                tex(AUTOMATION_FLAG_LABELS[flag]),
                integer(item["accounts"]),
                percent(item["account_share"]),
                integer(item["edge_events"]),
                percent(item["edge_event_share"]),
                rule,
            )
        )
    return rows


def automation_contrast_rows() -> list[tuple[str, ...]]:
    data = read_csv(
        "outputs/user_account_automation/addressed_edge_contrast_after_dropping_flagged.csv",
        ("cohort", "n_prs", "exposed_prs", "exposed_raw_merge_rate", "estimate", "ci_low", "ci_high", "dropped_prs"),
    )
    return [
        (
            comparison_math(item["cohort"]),
            integer(item["n_prs"]),
            integer(item["exposed_prs"]),
            percent(item["exposed_raw_merge_rate"]),
            pp(item["estimate"]),
            ci_pp(item["ci_low"], item["ci_high"]),
        )
        for item in data
    ]


def actors_note() -> str:
    summary = read_json("outputs/user_account_automation/summary.json")
    repetition = summary["addressed_edge_text_repetition"]
    note = (
        f"The rows of Panel C are the four pre-registered machine-likeness heuristics and the two combination rules, scored on the "
        f"{integer(summary['edge_writing_user_accounts'])} user accounts that write the "
        f"{integer(summary['edge_events_written_by_user_accounts'])} user-written addressed edges among the "
        f"{integer(summary['exposure_events_total'])} exposure events, using {integer(summary['comment_history_rows_scored'])} of their earlier comments. "
        f"An account is flagged when it trips at least two heuristics. The median machine-likeness score is {compact_number(summary['machine_likeness_score_median'], 3)} "
        f"and the maximum is {compact_number(summary['machine_likeness_score_max'], 3)}. "
        f"Of the {integer(repetition['edge_texts'])} edge texts, {integer(repetition['distinct_normalised_edge_texts'])} are distinct after normalisation "
        f"and the most repeated text appears {integer(repetition['most_frequent_count'])} times; hand reading of the "
        f"{integer(summary['manual_review_accounts'])} highest-scoring accounts finds that repetition to be hand-issued agent invocations and platform button text "
        "rather than generated output. Per-account scores and the hand-review sheet are in the public artifact."
    )
    return note


def matched_pair_rows() -> list[tuple[str, ...]]:
    summary = read_json("outputs/heterogeneity_audit/summary.json")
    overall = summary["part1_matched_pair_spread"]["overall_gap"]
    pairs = read_csv(
        "outputs/heterogeneity_audit/matched_pair_by_product_pair.csv",
        (
            "ordered_product_pair",
            "pairs",
            "repositories",
            "qualifies",
            "cross_rate",
            "same_rate",
            "paired_difference",
            "repository_cluster_ci_low",
            "repository_cluster_ci_high",
        ),
    )
    rows: list[tuple[str, ...]] = [
        (
            tex("All matched pairs (published gap)"),
            integer(overall["pairs"]),
            integer(overall["repositories"]),
            percent(overall["cross_rate"]),
            percent(overall["same_rate"]),
            pp(overall["paired_difference"])
            + " "
            + ci_pp(overall["repository_cluster_ci_low"], overall["repository_cluster_ci_high"]),
        )
    ]
    below: list[Mapping[str, str]] = []
    for item in pairs:
        if item["qualifies"] != "True":
            below.append(item)
            continue
        rows.append(
            (
                tex(item["ordered_product_pair"].replace("->", "to")),
                integer(item["pairs"]),
                integer(item["repositories"]),
                percent(item["cross_rate"]),
                percent(item["same_rate"]),
                pp(item["paired_difference"])
                + " "
                + ci_pp(item["repository_cluster_ci_low"], item["repository_cluster_ci_high"]),
            )
        )
    if not below:
        raise ValueError("Every ordered product pair now qualifies; the summary row is stale")
    rows.append(
        (
            tex(f"{len(below)} further pairs below the 30-pair floor"),
            integer(sum(number(item["pairs"]) for item in below)),
            "--",
            "--",
            "--",
            tex("not estimated"),
        )
    )
    return rows


def repository_moderator_rows() -> list[tuple[str, ...]]:
    models = read_csv(
        "outputs/heterogeneity_audit/rq3_moderator_models.csv",
        ("specification", "estimate", "ci_low", "ci_high", "share_of_primary_explained", "interval_excludes_zero"),
    )
    contrasts = read_csv(
        "outputs/heterogeneity_audit/moderator_group_contrasts.csv",
        (
            "moderator",
            "familiar_dominant_median",
            "newcomer_dominant_median",
            "median_difference",
            "repository_cluster_ci_low",
            "repository_cluster_ci_high",
            "separates_groups",
        ),
    )
    rows: list[tuple[str, ...]] = []
    for item in models:
        rows.append(
            (
                tex(item["specification"]),
                "--",
                "--",
                pp(item["estimate"]) + " pp",
                ci_pp(item["ci_low"], item["ci_high"]),
                percent(item["share_of_primary_explained"]) + tex("% explained"),
            )
        )
    moderator_labels = {
        "pre_total_prs": "Pull requests before the first trigger",
        "pre_distinct_contributors": "Distinct contributors before the first trigger",
        "pre_merge_rate": "Merge rate before the first trigger",
        "pre_reviews_per_pr": "Reviews per pull request before the first trigger",
        "pre_share_prs_any_review": "Share of pull requests with any review",
        "pre_repo_age_days": "Repository age in days at the first trigger",
    }
    for item in contrasts:
        moderator = item["moderator"]
        if moderator not in moderator_labels:
            raise ValueError(f"Unlabelled repository moderator: {moderator!r}")
        rows.append(
            (
                tex(moderator_labels[moderator]),
                f"{number(item['familiar_dominant_median']):.2f}",
                f"{number(item['newcomer_dominant_median']):.2f}",
                f"{number(item['median_difference']):.2f}",
                f"[{number(item['repository_cluster_ci_low']):.2f}, {number(item['repository_cluster_ci_high']):.2f}]",
                tex("separates" if item["separates_groups"] == "True" else "does not separate"),
            )
        )
    return rows


def heterogeneity_note() -> str:
    summary = read_json("outputs/heterogeneity_audit/summary.json")
    part1 = summary["part1_matched_pair_spread"]
    concentration = part1["concentration"]
    loo = part1["leave_one_out_ranges"]
    generality = part1["generality"]
    part2 = summary["part2_repository_moderators"]
    groups = part2["familiarity_group_counts"]
    qualifying = part1["qualifying_product_pairs"]
    excluding_zero = sum(
        1
        for item in qualifying
        if number(item["repository_cluster_ci_low"]) < 0 and number(item["repository_cluster_ci_high"]) < 0
    )
    note = (
        f"Panel B repeats the published gap inside each ordered product pair with at least "
        f"{integer(part1['minimum_pairs_per_product_pair'])} pairs; the frozen generality verdict is {generality['verdict']}, because every "
        f"leave-one-repository-out refit stays negative ({pp(loo['repository']['min'])} to {pp(loo['repository']['max'])} pp) and "
        f"{integer(generality['qualifying_product_pairs_negative'])} of {integer(generality['qualifying_product_pairs'])} qualifying pairs reproduce the sign, "
        f"while only {excluding_zero} pair has an interval excluding zero on its own. The pairs are unevenly spread: the largest repository holds "
        f"{percent(concentration['largest_repository_share'])}% of them, the largest ordered pair {percent(concentration['largest_product_pair_share'])}%, "
        f"the repository Gini is {compact_number(concentration['repository_gini'], 3)}, and the median is "
        f"{compact_number(concentration['median_pairs_per_repository'])} pairs per repository. Panel D gives the four familiar-versus-newcomer models in "
        "percentage points and then six pre-trigger repository descriptors, each in its own units and measured only on pull requests and reviews strictly "
        f"before each repository's first trigger. Group sizes are {integer(groups['familiar_dominant'])} familiar-dominant, "
        f"{integer(groups['newcomer_dominant'])} newcomer-dominant, {integer(groups['mixed_tie'])} tied, and {integer(groups['no_user_written_edge'])} "
        "repositories with no user-written edge. Per-repository descriptors and every leave-one-out refit are in the public artifact."
    )
    return note


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
    # A reader of the published Online Resource has no repository checkout, so no
    # internal artifact file name may reach the page. Line-breaking helpers slice
    # identifiers up, so the text is normalised before the gate is applied. The
    # ordered reproduction contract is the single documented exception: it names
    # the commands a reader runs, so ".py" stays legal.
    flattened = lowered.replace(r"\allowbreak{}", "").replace("\\_", "_").replace("\\", "")
    for extension in (".csv", ".parquet", ".json", ".tsv", ".jsonl", ".xlsx"):
        if extension in flattened:
            raise ValueError(
                f"Generated text names an internal artifact file ({extension}); "
                "describe the public artifact instead of a repository path"
            )
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
    ("rq1", (burst_table,)),
    ("rq2", (rq2_table,)),
    ("rq3", (addressed_edge_table, rq3_robustness_table)),
    ("specificity", (specificity_table,)),
    ("task_context", (task_context_table,)),
    ("external", (external_table,)),
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
