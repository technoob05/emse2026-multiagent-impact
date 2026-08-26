"""Build weighted, blinded task-continuity packets for two human coders."""

from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from multiagent_impact.task_continuity import AGENT_TEMPLATE  # noqa: E402


def blind_text(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = AGENT_TEMPLATE.sub("[AGENT]", text)
    text = re.sub(r"(?i)\b(?:merged?|closed|rejected|accepted)\b", "[OUTCOME]", text)
    return text[:4000]


def main(per_stratum: int = 15) -> None:
    config = AnalysisConfig.from_paths(ROOT)
    source = pl.read_parquet(ROOT / "outputs" / "cache" / "direct_continuity_candidates.parquet").to_pandas()
    source["path_class"] = np.where(source["shared_non_generic_files"] > 0, "non_generic", "generic_only")
    source["similarity_band"] = pd.cut(
        source["title_similarity"],
        [-0.001, 0.05, 0.10, 0.20, 1.001],
        labels=["very_low", "low", "medium", "high"],
    ).astype(str)
    source["agent_relation"] = np.where(source["changed_agent"], "new_agent", "same_agent")
    stratum_columns = ["agent_relation", "path_class", "similarity_band"]
    source["audit_stratum"] = source[stratum_columns].agg(" / ".join, axis=1)

    pieces = []
    for _, cell in source.groupby("audit_stratum", observed=True):
        n = min(per_stratum, len(cell))
        sampled = cell.sample(n=n, random_state=20260825).copy()
        sampled["stratum_population_n"] = len(cell)
        sampled["stratum_sample_n"] = n
        sampled["design_weight"] = len(cell) / n
        pieces.append(sampled)
    sample = pd.concat(pieces, ignore_index=True)

    ids = set(sample["failed_id"].astype(int)) | set(sample["successor_id"].astype(int))
    pr_text = (
        pl.scan_parquet(config.data_dir / "pull_request.parquet")
        .filter(pl.col("id").is_in(list(ids)))
        .select("id", "body")
        .collect(engine="streaming")
        .to_pandas()
    )
    prior_body = pr_text.rename(columns={"id": "failed_id", "body": "prior_body"})
    current_body = pr_text.rename(columns={"id": "successor_id", "body": "successor_body"})
    sample = sample.merge(prior_body, on="failed_id", how="left").merge(
        current_body, on="successor_id", how="left"
    )
    sample["prior_title_blind"] = sample["prior_title"].map(blind_text)
    sample["successor_title_blind"] = sample["current_title"].map(blind_text)
    sample["prior_body_blind"] = sample["prior_body"].map(blind_text)
    sample["successor_body_blind"] = sample["successor_body"].map(blind_text)
    sample["audit_id"] = [f"TC-{index:04d}" for index in range(1, len(sample) + 1)]

    packet_columns = [
        "audit_id", "audit_stratum", "stratum_population_n", "stratum_sample_n",
        "design_weight", "days_to_successor", "shared_files",
        "shared_non_generic_files", "example_shared_file", "prior_title_blind",
        "successor_title_blind", "prior_body_blind", "successor_body_blind",
    ]
    output_dir = ROOT / "outputs" / "human_audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    for coder, seed in [("A", 20260826), ("B", 20260827)]:
        packet = sample[packet_columns].sample(frac=1, random_state=seed).copy()
        packet["same_task"] = ""
        packet["confidence"] = ""
        packet["evidence_note"] = ""
        packet["intentional_handoff"] = ""
        packet["handoff_evidence"] = ""
        packet.to_csv(output_dir / f"coder_{coder}_blinded.csv", index=False, encoding="utf-8-sig")

    key_columns = [
        "audit_id", "failed_id", "successor_id", "repo_url", "prior_url", "current_url",
        "prior_agent", "current_agent", "same_contributor", "changed_agent",
        "recovered_within_30d", "audit_stratum", "design_weight",
    ]
    sample[key_columns].to_csv(output_dir / "audit_key_do_not_share_before_coding.csv", index=False, encoding="utf-8-sig")
    summary = (
        sample.groupby(stratum_columns, observed=True)
        .agg(population_n=("stratum_population_n", "first"), sample_n=("audit_id", "size"), weight=("design_weight", "first"))
        .reset_index()
    )
    summary.to_csv(output_dir / "sampling_design.csv", index=False)
    print(f"Built {len(sample):,} weighted cases across {len(summary)} strata in {output_dir}")


if __name__ == "__main__":
    main()
