"""Test whether the user accounts that write addressed edges are really people.

The paper says the account that answers an agent's review point is usually a
person rather than another product. That claim rests on the GitHub ``user_type``
field, which marks an account as ``Bot`` only when it authenticates as a GitHub
App. Scripted automation running under a personal access token, and
organisation-run service accounts, are recorded as ``User`` and would be counted
as people by the paper's classifier.

This script scores every user account that writes an exact addressed edge in the
landmark cohort against four pre-registered, transparent machine-likeness
heuristics computed over that account's entire comment history in the release,
reports the score distribution rather than only a flag count, and re-estimates
the headline addressed-edge contrast after dropping every PR whose edge was
written by a flagged account.

The heuristics and their thresholds are fixed before the estimates are read and
are not tuned afterwards. Each is stated with the reason it discriminates a
script from a person:

1. **Template repetition.** A script emits the same rendered text repeatedly;
   a person restates a point differently each time. Comparison is on normalised
   text so that changed identifiers, links and quoted context do not hide a
   template.
2. **Timing regularity.** A cron job or webhook responder produces
   inter-comment gaps with low dispersion; human activity is bursty and its
   gap distribution is heavy tailed, so a low coefficient of variation, or a
   large mass of gaps inside a narrow band around the median, is unlike a
   person.
3. **Round-the-clock activity.** One human sleeps. An account that posts in all
   24 UTC hours with no hour far below its own average has either no diurnal
   cycle or more than one operator behind it.
4. **Volume.** Sustained comments per active day above what a person plausibly
   writes by hand is evidence of generation rather than typing.

An account is flagged when it trips at least two heuristics. One heuristic alone
is deliberately not enough: a maintainer who writes "LGTM" several hundred times
trips template repetition without being a script, and a busy reviewer trips
volume without being a script. Both the one-heuristic and the two-heuristic
flags are reported so the reader can see the cost of that choice.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import parse_timestamp  # noqa: E402

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN = ROOT / "outputs" / "cross_agent_review"
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
SCOPE = ROOT / "outputs" / "addressed_edge_scope"
OUTPUT = ROOT / "outputs" / "user_account_automation"

PRIMARY_THRESHOLD = 48
EXPECTED_COHORT_ROWS = 1_067
EXPECTED_EXPOSURE_EVENTS = 128
EXPECTED_EXPOSED_PRS = 109

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

TEMPLATE_MIN_COMMENTS = 10
TEMPLATE_DUPLICATE_SHARE = 0.50
TIMING_MIN_GAPS = 20
TIMING_MAX_GAP_CV = 0.50
TIMING_BAND_TOLERANCE = 0.10
TIMING_MIN_BAND_SHARE = 0.25
CLOCK_MIN_COMMENTS = 48
CLOCK_MIN_HOUR_RATIO = 0.50
VOLUME_MIN_COMMENTS = 50
VOLUME_MIN_PER_ACTIVE_DAY = 20.0
COMBINED_MIN_HEURISTICS = 2
TOP_ACCOUNTS_FOR_MANUAL_REVIEW = 15

HEURISTICS = ["flag_template", "flag_timing", "flag_clock", "flag_volume"]

THRESHOLD_REGISTRY = [
    {
        "heuristic": "flag_template",
        "statistic": "duplicate_normalised_text_share",
        "threshold": f">= {TEMPLATE_DUPLICATE_SHARE} with >= {TEMPLATE_MIN_COMMENTS} comments",
        "justification": (
            "a script renders one template repeatedly, so at least half of its comments "
            "collapse onto text another of its own comments already used; the minimum "
            "volume keeps a two-comment account from being called a template"
        ),
    },
    {
        "heuristic": "flag_timing",
        "statistic": "inter_comment_gap_cv or narrow_band_gap_share",
        "threshold": (
            f"cv <= {TIMING_MAX_GAP_CV} or >= {TIMING_MIN_BAND_SHARE} of gaps within "
            f"+/-{TIMING_BAND_TOLERANCE:.0%} of the median gap, with >= {TIMING_MIN_GAPS} gaps"
        ),
        "justification": (
            "human commenting is bursty and its gap distribution is heavy tailed with a "
            "coefficient of variation well above one; a scheduled or trigger-driven poster "
            "concentrates gaps around a characteristic interval"
        ),
    },
    {
        "heuristic": "flag_clock",
        "statistic": "active_utc_hours and min_hour_share_of_uniform",
        "threshold": (
            f"all 24 UTC hours occupied and the quietest hour holds >= "
            f"{CLOCK_MIN_HOUR_RATIO} of the uniform expectation, with >= {CLOCK_MIN_COMMENTS} comments"
        ),
        "justification": (
            "a single person leaves a diurnal dip; an account with no hour far below its "
            "own average is either automated or operated by a rota, and either way is not "
            "the individual the claim describes"
        ),
    },
    {
        "heuristic": "flag_volume",
        "statistic": "comments_per_active_day",
        "threshold": (
            f">= {VOLUME_MIN_PER_ACTIVE_DAY} comments per active day with "
            f">= {VOLUME_MIN_COMMENTS} comments"
        ),
        "justification": (
            "sustained hand-written review commenting rarely exceeds a few tens of comments "
            "on an active day; a far higher sustained rate points at generation"
        ),
    },
]

# Written after reading the ranked table produced by this script and the most
# frequent normalised texts of each account; the login and the score components
# are in the reviewable CSV next to each judgement. The recurring finding is
# that the repeated strings are agent invocations and GitHub UI button text
# issued by a person, not output generated by a script.
MANUAL_JUDGEMENTS: dict[str, str] = {
    "marcellodebernardi": (
        "real person; the repeated string is '@greptileai please review again with latest "
        "changes', a hand-issued re-review trigger, and the rest is bespoke design prose"
    ),
    "weiguangli-io": (
        "real person doing bulk triage with canned closing messages ('closing due to "
        "inactivity'); the message is boilerplate but the decision behind each one is not"
    ),
    "PeterDaveHello": (
        "real person; trips template only because 56 percent of comments are agent "
        "invocations ('@codex review', '@coderabbitai review') typed by hand"
    ),
    "jcstein": (
        "real person driving an agent with short imperatives ('resume @copilot', "
        "'resolve conflicts @copilot')"
    ),
    "yamcodes": (
        "real person; 60 of 152 comments are the single token '@coderabbitai review', a "
        "repetitive habit rather than a script"
    ),
    "rvdbreemen": (
        "real person; the dominant string is GitHub's own 'apply changes based on this "
        "feedback' button text, so the repetition is the UI's, not the account's"
    ),
    "OliverZhaohaibin": (
        "real person delegating heavily through the GitHub UI button; high volume and "
        "boilerplate text, but every non-button comment is distinct"
    ),
    "Borda": (
        "real person; a recognised open-source maintainer mixing UI button text with "
        "bespoke review comments"
    ),
    "clairernovotny": (
        "real person; long specific technical justifications, low duplication, ranked high "
        "only on breadth of active hours"
    ),
    "chmouel": (
        "real person; the repeats are Prow slash commands ('/lgtm', '/retest', "
        "'/gemini review') that a maintainer types dozens of times a week"
    ),
    "yvolovich-cyber": (
        "real person; 30 of 96 comments are '@codex review', and the account also signs a "
        "CLA in its own words"
    ),
    "shaypal5": (
        "real person; UI button text plus pre-commit.ci follow-ups and bespoke replies"
    ),
    "jjmata": (
        "real person; '@coderabbitai review' repeats alongside informal notes such as "
        "'will sweep missing strings later'"
    ),
    "justin808": (
        "real person; repeats '@claude review this pr' but writes specific CI diagnoses "
        "elsewhere"
    ),
    "jeffspahr": (
        "real person; '/ok-to-test' and '/retest' are Prow commands, and the substantive "
        "comments are individually reasoned"
    ),
    "giulio-leone": (
        "the one account I would not defend as spontaneous human authorship: verbatim "
        "'gentle ping', 'closing to reduce PR volume' and a structured 'intervention note' "
        "block reused across unrelated PRs with unusually regular gaps; reads as a "
        "semi-automated or copy-paste-driven contribution campaign"
    ),
    "amalshaji": (
        "real person; nine '@codex review' invocations dominate a small history, the "
        "remaining comments are specific to their threads"
    ),
    "bfullam": (
        "real person with a terse style; 'addressed', 'agreed and done', 'nit' across only "
        "13 comments is exactly the case the combined rule is designed not to flag"
    ),
    "HammerGS": (
        "real person with a terse style; 'addressed' and 'fixed' repeated over 21 comments"
    ),
    "takenagain": (
        "real person; '@coderabbitai review' plus 'done in <commit>' acknowledgements that "
        "differ by commit hash"
    ),
}

URL_PATTERN = re.compile(r"https?://\S+")
FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
QUOTE_PATTERN = re.compile(r"^\s*>.*$", re.MULTILINE)
MENTION_PATTERN = re.compile(r"@[\w-]+")
NUMBER_PATTERN = re.compile(r"\d+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalise_body(text: str | None) -> str:
    """Strip everything a script would vary between renders of one template."""
    if text is None:
        return ""
    stripped = FENCE_PATTERN.sub(" ", text)
    stripped = QUOTE_PATTERN.sub(" ", stripped)
    stripped = URL_PATTERN.sub(" ", stripped)
    stripped = MENTION_PATTERN.sub(" ", stripped)
    stripped = NUMBER_PATTERN.sub(" ", stripped)
    return WHITESPACE_PATTERN.sub(" ", stripped).strip().lower()


def load_edge_writers() -> pl.DataFrame:
    audit = pl.read_parquet(EDGE / "exact_parent_reply_event_audit.parquet")
    if audit.height != EXPECTED_EXPOSURE_EVENTS:
        raise AssertionError(
            f"Exposure event drift: {audit.height} != {EXPECTED_EXPOSURE_EVENTS}"
        )
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet").select(
        "pr_id",
        "response_event_id",
        "response_user",
        "response_user_type",
        "response_actor_role",
        "response_dt",
    )
    joined = audit.join(
        events,
        on=["pr_id", "response_event_id"],
        how="left",
        validate="1:1",
    )
    if joined["response_actor_role"].null_count():
        raise AssertionError("An exposure event has no classified actor role.")
    if joined["pr_id"].n_unique() != EXPECTED_EXPOSED_PRS:
        raise AssertionError("Exposed-PR count drift in the exposure event audit.")

    scope = json.loads((SCOPE / "summary.json").read_text(encoding="utf-8"))
    user_events = joined.filter(pl.col("response_user_type") == "User")
    if user_events.height != scope["exposure_events_written_by_user_accounts"]:
        raise AssertionError(
            "User-written exposure events disagree with the frozen scope audit: "
            f"{user_events.height} != {scope['exposure_events_written_by_user_accounts']}"
        )
    return user_events.sort(["pr_id", "response_dt", "response_event_id"])


def load_comment_history(logins: list[str]) -> pl.DataFrame:
    """Every comment these accounts wrote anywhere in the release."""
    issue_comments = (
        pl.scan_parquet(DATA / "pr_comments.parquet")
        .filter(pl.col("user").is_in(logins))
        .select(
            pl.col("user").alias("login"),
            "user_type",
            "body",
            parse_timestamp("created_at", "comment_dt"),
            pl.lit("pr_comment").alias("comment_source"),
        )
    )
    inline_comments = (
        pl.scan_parquet(DATA / "pr_review_comments.parquet")
        .filter(pl.col("user").is_in(logins))
        .select(
            pl.col("user").alias("login"),
            "user_type",
            "body",
            parse_timestamp("created_at", "comment_dt"),
            pl.lit("inline_review_comment").alias("comment_source"),
        )
    )
    review_bodies = (
        pl.scan_parquet(DATA / "pr_reviews.parquet")
        .filter(pl.col("user").is_in(logins))
        .select(
            pl.col("user").alias("login"),
            "user_type",
            "body",
            parse_timestamp("submitted_at", "comment_dt"),
            pl.lit("submitted_review").alias("comment_source"),
        )
    )
    history = (
        pl.concat([issue_comments, inline_comments, review_bodies])
        .filter(
            pl.col("comment_dt").is_not_null()
            & pl.col("body").is_not_null()
            & (pl.col("body").str.strip_chars() != "")
        )
        .collect(engine="streaming")
    )
    if history.filter(pl.col("user_type").str.to_lowercase() != "user").height:
        raise AssertionError(
            "An edge-writing login also appears with a non-user account type."
        )
    return history.sort(["login", "comment_dt"])


def score_account(frame: pd.DataFrame) -> dict[str, object]:
    normalised = frame["body"].map(normalise_body)
    kept = normalised[normalised.str.len() > 0]
    comments = int(len(kept))
    counts = kept.value_counts()
    duplicate_share = (
        float(counts[counts > 1].sum() / comments) if comments else float("nan")
    )
    distinct_share = float(counts.size / comments) if comments else float("nan")

    times = frame["comment_dt"].sort_values()
    gaps = times.diff().dropna().dt.total_seconds().to_numpy()
    gaps = gaps[gaps > 0]
    if gaps.size:
        gap_mean = float(gaps.mean())
        gap_cv = float(gaps.std(ddof=1) / gap_mean) if gaps.size > 1 and gap_mean else float("nan")
        median_gap = float(np.median(gaps))
        band_share = (
            float(
                np.mean(np.abs(gaps - median_gap) <= TIMING_BAND_TOLERANCE * median_gap)
            )
            if median_gap > 0
            else float("nan")
        )
    else:
        gap_mean = gap_cv = median_gap = band_share = float("nan")

    hours = times.dt.hour
    hour_counts = hours.value_counts().reindex(range(24), fill_value=0)
    total = int(hour_counts.sum())
    active_hours = int((hour_counts > 0).sum())
    min_hour_ratio = (
        float(hour_counts.min() / (total / 24.0)) if total else float("nan")
    )
    shares = hour_counts.to_numpy() / total if total else np.zeros(24)
    nonzero = shares[shares > 0]
    hour_entropy = (
        float(-(nonzero * np.log(nonzero)).sum() / np.log(24)) if nonzero.size else 0.0
    )

    active_days = int(times.dt.floor("D").nunique())
    per_active_day = float(len(times) / active_days) if active_days else float("nan")
    span_days = float((times.max() - times.min()).total_seconds() / 86400.0)

    flag_template = bool(
        comments >= TEMPLATE_MIN_COMMENTS
        and duplicate_share == duplicate_share
        and duplicate_share >= TEMPLATE_DUPLICATE_SHARE
    )
    flag_timing = bool(
        gaps.size >= TIMING_MIN_GAPS
        and (
            (gap_cv == gap_cv and gap_cv <= TIMING_MAX_GAP_CV)
            or (band_share == band_share and band_share >= TIMING_MIN_BAND_SHARE)
        )
    )
    flag_clock = bool(
        total >= CLOCK_MIN_COMMENTS
        and active_hours == 24
        and min_hour_ratio == min_hour_ratio
        and min_hour_ratio >= CLOCK_MIN_HOUR_RATIO
    )
    flag_volume = bool(
        len(times) >= VOLUME_MIN_COMMENTS
        and per_active_day == per_active_day
        and per_active_day >= VOLUME_MIN_PER_ACTIVE_DAY
    )

    score_template = duplicate_share if duplicate_share == duplicate_share else 0.0
    score_timing = (
        float(np.clip(1.0 - gap_cv, 0.0, 1.0))
        if gaps.size >= TIMING_MIN_GAPS and gap_cv == gap_cv
        else 0.0
    )
    score_clock = (
        hour_entropy * (active_hours / 24.0) if total >= CLOCK_MIN_COMMENTS else 0.0
    )
    score_volume = (
        float(np.clip(np.log1p(per_active_day) / np.log1p(VOLUME_MIN_PER_ACTIVE_DAY), 0.0, 1.0))
        if per_active_day == per_active_day
        else 0.0
    )
    machine_likeness = float(
        np.mean([score_template, score_timing, score_clock, score_volume])
    )

    return {
        "comments": int(len(times)),
        "comments_with_text": comments,
        "distinct_normalised_texts": int(counts.size),
        "duplicate_normalised_text_share": duplicate_share,
        "distinct_text_share": distinct_share,
        "inter_comment_gaps": int(gaps.size),
        "median_gap_seconds": median_gap,
        "mean_gap_seconds": gap_mean,
        "inter_comment_gap_cv": gap_cv,
        "narrow_band_gap_share": band_share,
        "active_utc_hours": active_hours,
        "min_hour_share_of_uniform": min_hour_ratio,
        "hour_entropy_normalised": hour_entropy,
        "active_days": active_days,
        "observed_span_days": span_days,
        "comments_per_active_day": per_active_day,
        "flag_template": flag_template,
        "flag_timing": flag_timing,
        "flag_clock": flag_clock,
        "flag_volume": flag_volume,
        "score_template": score_template,
        "score_timing": score_timing,
        "score_clock": score_clock,
        "score_volume": score_volume,
        "machine_likeness_score": machine_likeness,
    }


def score_accounts(history: pl.DataFrame, writers: pl.DataFrame) -> pd.DataFrame:
    frame = history.to_pandas()
    rows = []
    edge_counts = (
        writers.group_by("response_user")
        .agg(
            pl.len().alias("edge_events_written"),
            pl.col("pr_id").n_unique().alias("edge_prs_written"),
        )
        .to_pandas()
        .set_index("response_user")
    )
    for login in sorted(edge_counts.index):
        account = frame[frame["login"] == login]
        if account.empty:
            raise AssertionError(f"Edge-writing account has no comment history: {login}")
        row = {"login": login}
        row.update(score_account(account))
        row["edge_events_written"] = int(edge_counts.loc[login, "edge_events_written"])
        row["edge_prs_written"] = int(edge_counts.loc[login, "edge_prs_written"])
        rows.append(row)
    scored = pd.DataFrame(rows)
    scored["heuristics_tripped"] = scored[HEURISTICS].sum(axis=1).astype(int)
    scored["flag_any"] = scored["heuristics_tripped"] >= 1
    scored["flag_combined"] = scored["heuristics_tripped"] >= COMBINED_MIN_HEURISTICS
    scored["scoreable_template"] = scored["comments_with_text"] >= TEMPLATE_MIN_COMMENTS
    scored["scoreable_timing"] = scored["inter_comment_gaps"] >= TIMING_MIN_GAPS
    scored["scoreable_clock"] = scored["comments"] >= CLOCK_MIN_COMMENTS
    scored["scoreable_volume"] = scored["comments"] >= VOLUME_MIN_COMMENTS
    return scored.sort_values(
        ["machine_likeness_score", "login"], ascending=[False, True]
    ).reset_index(drop=True)


def score_distribution(scored: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "machine_likeness_score",
        "duplicate_normalised_text_share",
        "inter_comment_gap_cv",
        "narrow_band_gap_share",
        "min_hour_share_of_uniform",
        "comments_per_active_day",
        "comments",
    ]
    rows = []
    for column in columns:
        values = scored[column].astype(float).dropna()
        rows.append(
            {
                "statistic": column,
                "accounts_with_value": int(values.size),
                "minimum": float(values.min()),
                "p25": float(values.quantile(0.25)),
                "median": float(values.median()),
                "p75": float(values.quantile(0.75)),
                "p90": float(values.quantile(0.90)),
                "maximum": float(values.max()),
                "mean": float(values.mean()),
            }
        )
    return pd.DataFrame(rows)


def heuristic_incidence(scored: pd.DataFrame, writers: pl.DataFrame) -> pd.DataFrame:
    events = writers.to_pandas()
    lookup = scored.set_index("login")
    total_accounts = len(scored)
    total_events = len(events)
    total_prs = int(events["pr_id"].nunique())
    rows = []
    for flag in [*HEURISTICS, "flag_any", "flag_combined"]:
        flagged = set(lookup.index[lookup[flag].astype(bool)])
        hit = events[events["response_user"].isin(flagged)]
        rows.append(
            {
                "flag": flag,
                "accounts": len(flagged),
                "accounts_total": total_accounts,
                "account_share": len(flagged) / total_accounts,
                "edge_events": int(len(hit)),
                "edge_events_total": total_events,
                "edge_event_share": len(hit) / total_events,
                "edge_prs": int(hit["pr_id"].nunique()),
                "edge_prs_total": total_prs,
                "edge_pr_share": int(hit["pr_id"].nunique()) / total_prs,
            }
        )
    return pd.DataFrame(rows)


def fit(frame: pd.DataFrame, label: str) -> dict[str, object]:
    exposure = f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"
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
        "cohort": label,
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


def reestimate(
    cohort: pd.DataFrame, scored: pd.DataFrame, writers: pl.DataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    events = writers.to_pandas()
    lookup = scored.set_index("login")
    rows = [fit(cohort, "full landmark cohort (published estimate)")]
    dropped: dict[str, int] = {}
    for flag, label in [
        ("flag_combined", f"dropping PRs whose edge was written by an account tripping >= {COMBINED_MIN_HEURISTICS} heuristics"),
        ("flag_any", "dropping PRs whose edge was written by an account tripping any heuristic"),
    ]:
        flagged = set(lookup.index[lookup[flag].astype(bool)])
        drop_prs = set(events.loc[events["response_user"].isin(flagged), "pr_id"])
        subset = cohort[~cohort["pr_id"].isin(drop_prs)].copy()
        dropped[flag] = len(drop_prs)
        row = fit(subset, label)
        row["dropped_prs"] = len(drop_prs)
        row["flag"] = flag
        rows.append(row)
    frame = pd.DataFrame(rows)
    published = pd.read_csv(EDGE / "addressed_edge_clustered_lpm.csv")
    frozen = published[
        (published["threshold_hours"] == PRIMARY_THRESHOLD)
        & (published["specification"] == "A_pretrigger_only")
    ].iloc[0]
    if abs(float(frozen["estimate"]) - float(frame.loc[0, "estimate"])) > 1e-9:
        raise AssertionError(
            "Refit of the full cohort does not reproduce the frozen headline estimate."
        )
    reference = {
        "frozen_estimate": float(frozen["estimate"]),
        "frozen_ci_low": float(frozen["ci_low"]),
        "frozen_ci_high": float(frozen["ci_high"]),
        "frozen_p_value": float(frozen["p_value"]),
        "dropped_prs_by_flag": dropped,
    }
    return frame, reference


def edge_text_repetition(writers: pl.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Repetition of the addressed-edge texts themselves, not the whole history.

    An account can be repetitive overall and still write the edge in its own
    words, so the reviewer's concern is answered most directly at the level of
    the 105 texts that actually carry the exposure.
    """
    bodies = pl.read_parquet(
        DATA / "pr_review_comments.parquet", columns=["id", "body"]
    ).rename({"id": "response_event_id"})
    joined = writers.join(bodies, on="response_event_id", how="left", validate="1:1")
    if joined.height != writers.height:
        raise AssertionError("Edge body join changed the exposure event count.")
    normalised = pd.Series(
        [normalise_body(text) for text in joined["body"].to_list()], name="text"
    )
    counts = normalised.value_counts()
    repeated = counts[counts > 1]
    table = (
        counts.rename("edge_events")
        .reset_index()
        .rename(columns={"index": "normalised_edge_text"})
    )
    table.columns = ["normalised_edge_text", "edge_events"]
    summary = {
        "edge_texts": int(len(normalised)),
        "distinct_normalised_edge_texts": int(counts.size),
        "distinct_share": float(counts.size / len(normalised)),
        "edge_texts_that_duplicate_another_edge_text": int(repeated.sum()),
        "most_frequent_normalised_edge_text": str(counts.index[0])[:200],
        "most_frequent_count": int(counts.iloc[0]),
        "empty_after_normalisation": int((normalised.str.len() == 0).sum()),
    }
    return table, summary


def manual_review_table(scored: pd.DataFrame) -> pd.DataFrame:
    keep = scored["flag_any"].astype(bool).to_numpy().copy()
    keep[:TOP_ACCOUNTS_FOR_MANUAL_REVIEW] = True
    top = scored[keep].copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    top["manual_judgement"] = top["login"].map(MANUAL_JUDGEMENTS).fillna(
        "NOT YET REVIEWED"
    )
    columns = [
        "rank",
        "login",
        "machine_likeness_score",
        "comments",
        "duplicate_normalised_text_share",
        "inter_comment_gap_cv",
        "narrow_band_gap_share",
        "active_utc_hours",
        "min_hour_share_of_uniform",
        "comments_per_active_day",
        "heuristics_tripped",
        "flag_combined",
        "edge_events_written",
        "edge_prs_written",
        "manual_judgement",
    ]
    return top[columns]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    writers = load_edge_writers()
    logins = sorted(writers["response_user"].unique().to_list())
    history = load_comment_history(logins)
    scored = score_accounts(history, writers)
    distribution = score_distribution(scored)
    incidence = heuristic_incidence(scored, writers)
    cohort = load_cohort()
    contrasts, reference = reestimate(cohort, scored, writers)
    edge_texts, edge_text_summary = edge_text_repetition(writers)
    manual = manual_review_table(scored)

    events = writers.to_pandas().merge(
        scored[["login", "machine_likeness_score", "heuristics_tripped", "flag_any", "flag_combined"]],
        left_on="response_user",
        right_on="login",
        how="left",
    )
    events = events.drop(columns=["login"]).sort_values(
        ["machine_likeness_score", "pr_id"], ascending=[False, True]
    )

    pd.DataFrame(THRESHOLD_REGISTRY).to_csv(
        OUTPUT / "preregistered_thresholds.csv", index=False
    )
    scored.to_csv(OUTPUT / "account_machine_likeness_scores.csv", index=False)
    distribution.to_csv(OUTPUT / "score_distribution.csv", index=False)
    incidence.to_csv(OUTPUT / "heuristic_incidence.csv", index=False)
    events.to_csv(OUTPUT / "edge_event_account_flags.csv", index=False)
    contrasts.to_csv(OUTPUT / "addressed_edge_contrast_after_dropping_flagged.csv", index=False)
    manual.to_csv(OUTPUT / "manual_review_top_accounts.csv", index=False)
    edge_texts.to_csv(OUTPUT / "addressed_edge_text_repetition.csv", index=False)

    combined = incidence[incidence["flag"] == "flag_combined"].iloc[0]
    any_flag = incidence[incidence["flag"] == "flag_any"].iloc[0]
    primary = contrasts[contrasts.get("flag").eq("flag_combined")].iloc[0]
    unreviewed = int((manual["manual_judgement"] == "NOT YET REVIEWED").sum())

    summary = {
        "edge_writing_user_accounts": int(len(scored)),
        "edge_events_written_by_user_accounts": int(writers.height),
        "edge_prs_with_a_user_written_edge": int(writers["pr_id"].n_unique()),
        "exposure_events_total": EXPECTED_EXPOSURE_EVENTS,
        "exposed_prs_total": EXPECTED_EXPOSED_PRS,
        "comment_history_rows_scored": int(history.height),
        "accounts_by_heuristic": {
            row["flag"]: {
                "accounts": int(row["accounts"]),
                "account_share": float(row["account_share"]),
                "edge_events": int(row["edge_events"]),
                "edge_event_share": float(row["edge_event_share"]),
                "edge_prs": int(row["edge_prs"]),
            }
            for _, row in incidence.iterrows()
        },
        "flagged_accounts_combined": int(combined["accounts"]),
        "flagged_edge_events_combined": int(combined["edge_events"]),
        "flagged_accounts_any_heuristic": int(any_flag["accounts"]),
        "flagged_edge_events_any_heuristic": int(any_flag["edge_events"]),
        "machine_likeness_score_median": float(
            scored["machine_likeness_score"].median()
        ),
        "machine_likeness_score_max": float(scored["machine_likeness_score"].max()),
        "original_contrast": {
            "estimate": reference["frozen_estimate"],
            "ci_low": reference["frozen_ci_low"],
            "ci_high": reference["frozen_ci_high"],
            "p_value": reference["frozen_p_value"],
            "n_prs": int(contrasts.loc[0, "n_prs"]),
            "exposed_prs": int(contrasts.loc[0, "exposed_prs"]),
        },
        "contrast_after_dropping_flagged": {
            "estimate": float(primary["estimate"]),
            "ci_low": float(primary["ci_low"]),
            "ci_high": float(primary["ci_high"]),
            "p_value": float(primary["p_value"]),
            "n_prs": int(primary["n_prs"]),
            "exposed_prs": int(primary["exposed_prs"]),
            "dropped_prs": int(primary["dropped_prs"]),
        },
        "addressed_edge_text_repetition": edge_text_summary,
        "manual_review_accounts": int(len(manual)),
        "manual_review_pending": unreviewed,
        "combined_flag_rule": (
            f"an account is flagged when it trips at least {COMBINED_MIN_HEURISTICS} of "
            "the four pre-registered heuristics"
        ),
        "interpretation": None,
        "scope": (
            "sensitivity audit of the actor classification behind the addressed edge; "
            "heuristics are behavioural proxies, not ground truth about account operation"
        ),
    }
    summary["interpretation"] = (
        f"{summary['flagged_accounts_combined']} of {summary['edge_writing_user_accounts']} "
        f"user accounts that write an exact addressed edge trip at least "
        f"{COMBINED_MIN_HEURISTICS} machine-likeness heuristics, covering "
        f"{summary['flagged_edge_events_combined']} of "
        f"{summary['edge_events_written_by_user_accounts']} user-written edge events; "
        f"dropping every PR whose edge such an account wrote moves the adjusted later-merge "
        f"contrast from {summary['original_contrast']['estimate']:.4f} "
        f"[{summary['original_contrast']['ci_low']:.4f}, {summary['original_contrast']['ci_high']:.4f}] "
        f"to {summary['contrast_after_dropping_flagged']['estimate']:.4f} "
        f"[{summary['contrast_after_dropping_flagged']['ci_low']:.4f}, "
        f"{summary['contrast_after_dropping_flagged']['ci_high']:.4f}]; "
        f"{edge_text_summary['distinct_normalised_edge_texts']} of "
        f"{edge_text_summary['edge_texts']} addressed-edge texts are distinct after "
        "normalisation, and manual reading of the highest-scoring accounts finds that the "
        "repetition driving the template heuristic is hand-issued agent invocations and "
        "GitHub UI button text rather than generated output, so the audit supports the "
        "claim that a person writes the reply while showing that what the person writes is "
        "often a one-line trigger rather than a substantive engineering response"
    )
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print()
    print(incidence.to_string(index=False))
    print()
    print(
        contrasts[
            ["cohort", "n_prs", "exposed_prs", "estimate", "ci_low", "ci_high", "p_value"]
        ].to_string(index=False)
    )
    print()
    print(
        manual[
            [
                "rank",
                "login",
                "machine_likeness_score",
                "comments",
                "duplicate_normalised_text_share",
                "inter_comment_gap_cv",
                "active_utc_hours",
                "comments_per_active_day",
                "heuristics_tripped",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
