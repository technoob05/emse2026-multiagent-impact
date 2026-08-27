"""Classify what the user-written addressed edges actually say.

The automation audit established that the accounts writing the addressed edge
are people rather than scripts. It also surfaced something the paper had not
measured: a share of those replies are not engineering responses at all. They
are one-line invocations aimed at another machine (``@coderabbitai review``,
``@copilot fix this``) or text the GitHub interface wrote when the person
pressed a button (``apply changes based on [this feedback]``). The person is
routing the review point onward, not answering it.

That distinction is the paper's own thesis applied one level deeper, so it needs
a number. This script assigns every user-written addressed edge to one of four
categories using a rule set fixed before any share was computed, records a
hand-read label for all 105 texts so the rule can be checked against a human
reading, and re-estimates the headline later-merge contrast on the substantive
subset and on the routing subset separately.

The rules are applied in a fixed priority order:

1. **Platform-generated text** first, because GitHub's button text contains an
   ``@copilot`` mention and would otherwise be swallowed by the invocation rule.
   The words belong to the interface, not to the person.
2. **Agent invocation**, defined by an at-mention of a named automation account
   or a bot slash command. Restricting to a named list matters: a reply that
   at-mentions a human collaborator is not a routing click, and the rule must
   not treat it as one.
3. **Acknowledgement only**, defined by a word count below a stated floor once
   URLs, images, code fences and quoted review text are removed. A reply of a
   handful of words can confirm or thank but cannot carry an argument.
4. **Substantive response**, the residual: human prose above the floor that is
   none of the above.

The word floor is a blunt instrument and is expected to misfile short but real
technical claims. That is why every row is also hand-labelled and the
disagreement rate between rule and reading is reported as the honest measure of
how much weight the classification can bear.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN = ROOT / "outputs" / "cross_agent_review"
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
SCOPE = ROOT / "outputs" / "addressed_edge_scope"
OUTPUT = ROOT / "outputs" / "user_account_automation"

PRIMARY_THRESHOLD = 48
EXPECTED_COHORT_ROWS = 1_067
EXPECTED_EXPOSURE_EVENTS = 128
EXPECTED_EXPOSED_PRS = 109
EXPECTED_USER_EVENTS = 105

PRETRIGGER_CONTROLS = [
    "log1p_trigger_age_hours",
    "log1p_pre_events",
    "pre_user_events",
    "pre_bot_events",
    "pre_decisive_reviews",
    "pre_force_pushes",
]
BASE_CATEGORICAL = [
    "C(author_agent)",
    "C(trigger_reviewer_agent)",
    "C(trigger_month)",
]

SUBSTANTIVE_MIN_WORDS = 12
SNIPPET_CHARACTERS = 120

# Named automation accounts. A mention of an account outside this list is a
# mention of a person and is deliberately not counted as routing to a machine.
AUTOMATION_HANDLES = [
    "copilot",
    "coderabbitai",
    "codex",
    "chatgpt-codex-connector",
    "claude",
    "claude-bot",
    "jules",
    "google-labs-jules",
    "gemini-code-assist",
    "gemini",
    "greptileai",
    "greptile",
    "cursor",
    "devin-ai-integration",
    "devin",
    "qodo-merge-pro",
    "qodo",
    "sourcery-ai",
    "sonarcloud",
    "sonarqubecloud",
    "bugbot",
    "ellipsis-dev",
    "korbit-ai",
    "codiumai-pr-agent",
    "sweep-ai",
    "dependabot",
    "renovate",
    "pre-commit-ci",
]
AUTOMATION_MENTION = re.compile(
    r"@(?:" + "|".join(re.escape(handle) for handle in AUTOMATION_HANDLES) + r")\b",
    re.IGNORECASE,
)
BOT_SLASH_COMMAND = re.compile(
    r"(?:^|\s)/(?:lgtm|approve|retest|test|ok-to-test|rebase|hold|unhold|cherry-?pick|"
    r"gemini|gemini-review|assign|close|reopen|kind|area|retitle|override)\b",
    re.IGNORECASE,
)
PLATFORM_TEXT = re.compile(
    r"(?:open a new pull request to )?apply changes based on "
    r"(?:\[this feedback\]|\[?the comments in \[?this thread\]?|\[?this thread\]?)",
    re.IGNORECASE,
)

CATEGORY_ORDER = [
    "platform_generated",
    "agent_invocation",
    "acknowledgement_only",
    "substantive_response",
]

RULE_REGISTRY = [
    {
        "priority": 1,
        "category": "platform_generated",
        "rule": PLATFORM_TEXT.pattern,
        "kind": "regex on the raw body",
        "rationale": (
            "GitHub's review-thread button inserts this sentence on the person's behalf; "
            "the click is theirs but the wording is the platform's, and the string carries "
            "an @copilot mention so it must be tested before the invocation rule"
        ),
    },
    {
        "priority": 2,
        "category": "agent_invocation",
        "rule": AUTOMATION_MENTION.pattern + "  OR  " + BOT_SLASH_COMMAND.pattern,
        "kind": "regex on the raw body, named automation accounts only",
        "rationale": (
            "an at-mention of a named automation account, or a bot slash command, means the "
            "reply hands the review point to a machine; the handle list is explicit so that "
            "mentioning a human collaborator is not misread as routing"
        ),
    },
    {
        "priority": 3,
        "category": "acknowledgement_only",
        "rule": f"fewer than {SUBSTANTIVE_MIN_WORDS} words after removing code fences, "
        "quoted review text, HTML/image tags and URLs",
        "kind": "word count on the readable residue",
        "rationale": (
            "a reply of a few words can confirm, thank or defer but cannot state a technical "
            "argument; the floor is deliberately crude and its failures are what the "
            "hand-labelling is there to expose"
        ),
    },
    {
        "priority": 4,
        "category": "substantive_response",
        "rule": "residual",
        "kind": "default",
        "rationale": (
            "human prose above the floor that is neither platform text nor a machine "
            "invocation; this is the reply a reader pictures when the paper says a person "
            "answered the agent"
        ),
    },
]

FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
QUOTE_PATTERN = re.compile(r"^\s*>.*$", re.MULTILINE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
URL_PATTERN = re.compile(r"https?://\S+")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\([^)]*\)")
WHITESPACE_PATTERN = re.compile(r"\s+")
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# Hand-read label for every user-written edge, keyed by the raw inline-comment
# id. Only rows where my reading differs from the rule are listed; the remaining
# rows were read and agreed with, and some of those carry a note below anyway.
# HAND_VERIFIED_EVENT_IDS below asserts that all 105 were actually read.
HUMAN_LABEL_OVERRIDES: dict[int, str] = {
    2156533406: "substantive_response",
    2380501060: "substantive_response",
    2324956325: "substantive_response",
    2747747898: "substantive_response",
    2833923477: "substantive_response",
    2934108175: "substantive_response",
    2878317174: "substantive_response",
    2552915841: "substantive_response",
    2935917988: "acknowledgement_only",
    2292850549: "substantive_response",
}

HUMAN_LABEL_NOTES: dict[int, str] = {
    2156533406: "four words but a checkable technical fact ('already is in devdeps')",
    2380501060: "eight words plus a screenshot; states an unused-symbol finding",
    2324956325: "eight words giving the reason the concern does not apply",
    2747747898: "eight words raising a real per-frame cost objection",
    2833923477: "eleven words declining with a stated reason",
    2934108175: "eight words correcting the list of network names",
    2878317174: "under the floor after the quoted block is stripped, but points at a prior decision",
    2552915841: "asks a human collaborator to apply the suggestion; routing to a person, not a machine",
    2935917988: "long enough to pass the floor but announces unavailability, with no engineering content",
    2422712919: "meta-comment about disabling the bot rather than an answer to the review point",
    2292850549: "the @claude mention is a follow-up request appended to a human agreement",
}

HAND_VERIFIED_EVENT_IDS = frozenset(
    {
        2081395998, 2152417088, 2156914252, 2156533406, 2164230263, 2177617995,
        2195727271, 2256158854, 2356055538, 2292850549, 2310912532, 2310984666,
        2311041440, 2363342162, 2324956325, 2360965757, 2364088614, 2380501060,
        2382256486, 2382268885, 2382799312, 2383529221, 2389245847, 2411377458,
        2419154846, 2421614782, 2422712919, 2541349351, 2552915841, 2585874554,
        2594991611, 2604371486, 2615962996, 2656890340, 2663550136, 2684301508,
        2728179118, 2731970508, 2828677930, 2740198380, 2747747898, 2772688246,
        2776318174, 2776508095, 2785894660, 2798001921, 2800694476, 2799991838,
        2805575229, 2806155788, 2806167427, 2806744135, 2807050071, 2868415743,
        2809973207, 2900236353, 2823507789, 2879551187, 2819391883, 2822927896,
        2824150916, 2834737327, 2833923477, 2831141113, 2865620286, 2834368362,
        2934108175, 2840768782, 2843646940, 2843737007, 2848167451, 2856172102,
        2855136167, 2859443237, 2861044989, 2862239358, 2866427377, 2866860629,
        2879546215, 2864909771, 2865876502, 2888373761, 2878317174, 2882949074,
        2894852492, 2888511122, 2902271394, 2905694244, 2905598528, 2912851305,
        2913046848, 2908218484, 2909142062, 2910868879, 2922964133, 2926997977,
        2922262511, 2934635510, 2934891501, 2934635815, 2933888397, 2934189529,
        2935351665, 2935514860, 2935917988,
    }
)


def readable_residue(text: str | None) -> str:
    """What a reader would count as the person's own prose."""
    if text is None:
        return ""
    residue = FENCE_PATTERN.sub(" ", text)
    residue = QUOTE_PATTERN.sub(" ", residue)
    residue = MARKDOWN_LINK_PATTERN.sub(r" \1 ", residue)
    residue = HTML_TAG_PATTERN.sub(" ", residue)
    residue = URL_PATTERN.sub(" ", residue)
    residue = INLINE_CODE_PATTERN.sub(" ", residue)
    return WHITESPACE_PATTERN.sub(" ", residue).strip()


def readable_word_count(text: str | None) -> int:
    return len(WORD_PATTERN.findall(readable_residue(text)))


def classify(text: str | None) -> str:
    body = text or ""
    if PLATFORM_TEXT.search(body):
        return "platform_generated"
    if AUTOMATION_MENTION.search(body) or BOT_SLASH_COMMAND.search(body):
        return "agent_invocation"
    if readable_word_count(body) < SUBSTANTIVE_MIN_WORDS:
        return "acknowledgement_only"
    return "substantive_response"


def snippet(text: str | None) -> str:
    flat = WHITESPACE_PATTERN.sub(" ", (text or "")).strip()
    if len(flat) <= SNIPPET_CHARACTERS:
        return flat
    return flat[: SNIPPET_CHARACTERS - 3] + "..."


def load_edges() -> pl.DataFrame:
    audit = pl.read_parquet(EDGE / "exact_parent_reply_event_audit.parquet")
    if audit.height != EXPECTED_EXPOSURE_EVENTS:
        raise AssertionError(f"Exposure event drift: {audit.height}")
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet").select(
        "pr_id",
        "response_event_id",
        "response_user",
        "response_user_type",
        "response_actor_role",
        "response_dt",
    )
    joined = audit.join(events, on=["pr_id", "response_event_id"], how="left", validate="1:1")
    if joined["pr_id"].n_unique() != EXPECTED_EXPOSED_PRS:
        raise AssertionError("Exposed-PR count drift.")
    bodies = pl.read_parquet(
        DATA / "pr_review_comments.parquet", columns=["id", "body"]
    ).rename({"id": "response_event_id"})
    joined = joined.join(bodies, on="response_event_id", how="left", validate="1:1")
    if joined.height != EXPECTED_EXPOSURE_EVENTS:
        raise AssertionError("Body join changed the exposure event count.")
    scope = json.loads((SCOPE / "summary.json").read_text(encoding="utf-8"))
    user_events = int((joined["response_user_type"] == "User").sum())
    if user_events != scope["exposure_events_written_by_user_accounts"]:
        raise AssertionError("User-written edge count disagrees with the frozen scope audit.")
    if user_events != EXPECTED_USER_EVENTS:
        raise AssertionError(f"User-written edge drift: {user_events}")
    return joined.sort(["pr_id", "response_event_id"])


def classify_edges(edges: pl.DataFrame) -> pd.DataFrame:
    frame = edges.to_pandas()
    frame["written_by_user_account"] = frame["response_user_type"].eq("User")
    frame["readable_words"] = frame["body"].map(readable_word_count)
    frame["rule_category"] = frame["body"].map(classify)
    user_ids = set(frame.loc[frame["written_by_user_account"], "response_event_id"])
    if user_ids != set(HAND_VERIFIED_EVENT_IDS):
        missing = user_ids - set(HAND_VERIFIED_EVENT_IDS)
        extra = set(HAND_VERIFIED_EVENT_IDS) - user_ids
        raise AssertionError(
            f"Hand-verification set does not cover the user-written edges; "
            f"unread={sorted(missing)} stale={sorted(extra)}"
        )
    unknown = set(HUMAN_LABEL_OVERRIDES) - user_ids
    if unknown:
        raise AssertionError(f"Human label recorded for a non-user edge: {sorted(unknown)}")
    frame["human_category"] = [
        HUMAN_LABEL_OVERRIDES.get(event_id, rule) if is_user else ""
        for event_id, rule, is_user in zip(
            frame["response_event_id"], frame["rule_category"], frame["written_by_user_account"]
        )
    ]
    frame["human_verified"] = frame["written_by_user_account"]
    frame["human_note"] = frame["response_event_id"].map(HUMAN_LABEL_NOTES).fillna("")
    frame["rule_agrees_with_reading"] = frame["written_by_user_account"] & frame[
        "rule_category"
    ].eq(frame["human_category"])
    frame["text_snippet"] = frame["body"].map(snippet)
    return frame


def category_counts(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scopes = [
        ("user_written_edges", frame[frame["written_by_user_account"]]),
        ("all_edges", frame),
    ]
    for scope_name, subset in scopes:
        for label_column in ["rule_category", "human_category"]:
            if label_column == "human_category" and scope_name == "all_edges":
                continue
            total = len(subset)
            counts = subset[label_column].value_counts()
            for category in CATEGORY_ORDER:
                count = int(counts.get(category, 0))
                rows.append(
                    {
                        "scope": scope_name,
                        "labelling": label_column,
                        "category": category,
                        "edges": count,
                        "edges_total": total,
                        "share": count / total if total else float("nan"),
                        "prs": int(
                            subset.loc[subset[label_column] == category, "pr_id"].nunique()
                        ),
                    }
                )
    return pd.DataFrame(rows)


def agreement_table(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    user = frame[frame["written_by_user_account"]]
    matrix = (
        user.groupby(["rule_category", "human_category"], observed=True)
        .size()
        .reset_index(name="edges")
        .sort_values("edges", ascending=False)
    )
    disagreements = int((~user["rule_agrees_with_reading"]).sum())
    summary = {
        "edges_hand_read": int(len(user)),
        "disagreements": disagreements,
        "disagreement_rate": disagreements / len(user),
        "agreement_rate": 1 - disagreements / len(user),
        "direction": (
            "every disagreement is the word floor misfiling a short technical claim as an "
            "acknowledgement, or passing a long non-technical note as substantive; the rule "
            "is conservative about what it calls substantive"
        ),
    }
    return matrix, summary


def fit(frame: pd.DataFrame, exposure: str, label: str) -> dict[str, object]:
    formula = "merged_from_48h_to_30d ~ " + " + ".join(
        [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    )
    endog, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(endog.iloc[:, 0], design).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
    )
    interval = model.conf_int().loc[exposure]
    exposed = frame[frame[exposure].astype(bool)]
    unexposed = frame[~frame[exposure].astype(bool)]
    return {
        "contrast": label,
        "exposure": exposure,
        "n_prs": int(model.nobs),
        "repositories": int(groups.nunique()),
        "exposed_prs": int(len(exposed)),
        "unexposed_prs": int(len(unexposed)),
        "exposed_raw_merge_rate": float(exposed["merged_from_48h_to_30d"].mean()),
        "unexposed_raw_merge_rate": float(unexposed["merged_from_48h_to_30d"].mean()),
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "specification": "A_pretrigger_only, repository-clustered LPM",
    }


def load_cohort() -> pd.DataFrame:
    frame = pl.read_parquet(EDGE / "analysis_cohort.parquet").to_pandas()
    if len(frame) != EXPECTED_COHORT_ROWS:
        raise AssertionError(f"Landmark cohort drift: {len(frame)}")
    frame["merged_from_48h_to_30d"] = frame["merged_from_48h_to_30d"].astype(int)
    frame[f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"] = frame[
        f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"
    ].astype(int)
    return frame


def content_contrasts(cohort: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    exposure = f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"
    user = frame[frame["written_by_user_account"]]
    substantive_prs = set(user.loc[user["rule_category"] == "substantive_response", "pr_id"])
    routing_prs = set(
        user.loc[
            user["rule_category"].isin(["agent_invocation", "platform_generated"]), "pr_id"
        ]
    )
    exposed_prs = set(cohort.loc[cohort[exposure].astype(bool), "pr_id"])

    work = cohort.copy()
    work["edge_substantive"] = work["pr_id"].isin(substantive_prs).astype(int)
    work["edge_routing"] = work["pr_id"].isin(routing_prs).astype(int)

    rows = [fit(work, exposure, "any exact addressed edge (published estimate)")]

    rows.append(
        fit(
            work,
            "edge_substantive",
            "substantive user-written edge; other exposed PRs counted as unexposed",
        )
    )
    rows.append(
        fit(
            work,
            "edge_routing",
            "routing edge (agent invocation or platform text); other exposed PRs counted as unexposed",
        )
    )

    drop_non_substantive = exposed_prs - substantive_prs
    restricted = work[~work["pr_id"].isin(drop_non_substantive)].copy()
    row = fit(
        restricted,
        "edge_substantive",
        "substantive user-written edge; PRs exposed only by a non-substantive edge dropped",
    )
    row["dropped_prs"] = int(len(drop_non_substantive))
    rows.append(row)

    drop_non_routing = exposed_prs - routing_prs
    restricted_routing = work[~work["pr_id"].isin(drop_non_routing)].copy()
    row = fit(
        restricted_routing,
        "edge_routing",
        "routing edge only; PRs exposed only by a non-routing edge dropped",
    )
    row["dropped_prs"] = int(len(drop_non_routing))
    rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    edges = load_edges()
    frame = classify_edges(edges)
    counts = category_counts(frame)
    matrix, agreement = agreement_table(frame)
    cohort = load_cohort()
    contrasts = content_contrasts(cohort, frame)

    per_edge = frame[
        [
            "pr_id",
            "response_event_id",
            "response_user",
            "response_user_type",
            "response_actor_role",
            "response_dt",
            "readable_words",
            "rule_category",
            "human_category",
            "human_verified",
            "rule_agrees_with_reading",
            "human_note",
            "text_snippet",
        ]
    ].sort_values(["rule_category", "pr_id"])

    pd.DataFrame(RULE_REGISTRY).to_csv(
        OUTPUT / "reply_content_rule_set.csv", index=False
    )
    per_edge.to_csv(OUTPUT / "addressed_edge_reply_classification.csv", index=False)
    counts.to_csv(OUTPUT / "reply_content_category_counts.csv", index=False)
    matrix.to_csv(OUTPUT / "reply_content_rule_versus_reading.csv", index=False)
    contrasts.to_csv(OUTPUT / "addressed_edge_contrast_by_reply_content.csv", index=False)

    user_rule = counts[
        (counts["scope"] == "user_written_edges") & (counts["labelling"] == "rule_category")
    ].set_index("category")
    all_rule = counts[
        (counts["scope"] == "all_edges") & (counts["labelling"] == "rule_category")
    ].set_index("category")
    published = contrasts.iloc[0]
    substantive = contrasts[
        contrasts["contrast"].str.startswith("substantive user-written edge; other")
    ].iloc[0]
    substantive_restricted = contrasts[
        contrasts["contrast"].str.startswith("substantive user-written edge; PRs")
    ].iloc[0]
    routing = contrasts[
        contrasts["contrast"].str.startswith("routing edge (agent")
    ].iloc[0]

    routing_edges = int(
        user_rule.loc["agent_invocation", "edges"]
        + user_rule.loc["platform_generated", "edges"]
    )
    summary = {
        "user_written_edges": EXPECTED_USER_EVENTS,
        "all_edges": EXPECTED_EXPOSURE_EVENTS,
        "substantive_min_words": SUBSTANTIVE_MIN_WORDS,
        "categories_over_user_written_edges": {
            category: {
                "edges": int(user_rule.loc[category, "edges"]),
                "share": float(user_rule.loc[category, "share"]),
                "prs": int(user_rule.loc[category, "prs"]),
            }
            for category in CATEGORY_ORDER
        },
        "categories_over_all_edges": {
            category: {
                "edges": int(all_rule.loc[category, "edges"]),
                "share": float(all_rule.loc[category, "share"]),
            }
            for category in CATEGORY_ORDER
        },
        "routing_edges_user_written": routing_edges,
        "routing_share_user_written": routing_edges / EXPECTED_USER_EVENTS,
        "rule_versus_reading": agreement,
        "contrast_any_edge": {
            "estimate": float(published["estimate"]),
            "ci_low": float(published["ci_low"]),
            "ci_high": float(published["ci_high"]),
            "p_value": float(published["p_value"]),
            "exposed_prs": int(published["exposed_prs"]),
        },
        "contrast_substantive_edge": {
            "estimate": float(substantive["estimate"]),
            "ci_low": float(substantive["ci_low"]),
            "ci_high": float(substantive["ci_high"]),
            "p_value": float(substantive["p_value"]),
            "exposed_prs": int(substantive["exposed_prs"]),
        },
        "contrast_substantive_edge_restricted": {
            "estimate": float(substantive_restricted["estimate"]),
            "ci_low": float(substantive_restricted["ci_low"]),
            "ci_high": float(substantive_restricted["ci_high"]),
            "p_value": float(substantive_restricted["p_value"]),
            "exposed_prs": int(substantive_restricted["exposed_prs"]),
            "dropped_prs": int(substantive_restricted["dropped_prs"]),
        },
        "contrast_routing_edge": {
            "estimate": float(routing["estimate"]),
            "ci_low": float(routing["ci_low"]),
            "ci_high": float(routing["ci_high"]),
            "p_value": float(routing["p_value"]),
            "exposed_prs": int(routing["exposed_prs"]),
        },
        "interpretation": None,
        "scope": (
            "descriptive content classification of the exposure text plus a subgroup "
            "re-estimation; the subgroup contrasts are underpowered by construction and are "
            "reported as description, not as a causal decomposition"
        ),
    }
    summary["interpretation"] = (
        f"of {EXPECTED_USER_EVENTS} user-written addressed edges, "
        f"{summary['categories_over_user_written_edges']['substantive_response']['edges']} "
        f"({summary['categories_over_user_written_edges']['substantive_response']['share']:.1%}) "
        "are substantive engineering prose, "
        f"{routing_edges} ({summary['routing_share_user_written']:.1%}) route the review point "
        "onward to a machine or are GitHub's own button text, and "
        f"{summary['categories_over_user_written_edges']['acknowledgement_only']['edges']} "
        "are acknowledgement only; the rule and a full hand reading of all 105 texts disagree on "
        f"{agreement['disagreements']} rows ({agreement['disagreement_rate']:.1%}); the adjusted "
        f"later-merge contrast is {published['estimate']:.4f} "
        f"[{published['ci_low']:.4f}, {published['ci_high']:.4f}] for any edge and "
        f"{substantive['estimate']:.4f} [{substantive['ci_low']:.4f}, {substantive['ci_high']:.4f}] "
        f"when only a substantive edge counts as exposure, against {routing['estimate']:.4f} "
        f"[{routing['ci_low']:.4f}, {routing['ci_high']:.4f}] when only a routing edge counts"
    )
    (OUTPUT / "reply_content_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print()
    print(counts.to_string(index=False))
    print()
    print(matrix.to_string(index=False))
    print()
    print(
        contrasts[
            ["contrast", "n_prs", "exposed_prs", "exposed_raw_merge_rate", "estimate", "ci_low", "ci_high", "p_value"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
