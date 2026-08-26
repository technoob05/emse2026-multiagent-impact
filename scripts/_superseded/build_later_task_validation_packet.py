from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig, DATASET_REVISION  # noqa: E402
from multiagent_impact.specialization import classify_title  # noqa: E402


SEED = 20260825
TARGET_PER_STRATUM = 15
ALLOWED_LABELS = "feat | fix | docs | test | maintenance | unclear"


def stable_code(pr_id: int) -> str:
    digest = hashlib.sha256(f"{SEED}:{pr_id}".encode("utf-8")).hexdigest()[:10]
    return f"TASK-{digest.upper()}"


def sample_packet(data_dir: Path, predictions_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = [
        "id",
        "agent",
        "title",
        "body",
        "created_at",
        "repo_url",
        "html_url",
    ]
    frame = pd.read_parquet(data_dir / "pull_request.parquet", columns=columns)
    predictions = pd.read_parquet(predictions_path)
    frame = frame.merge(predictions, on="id", how="left", validate="one_to_one")
    frame["created_dt"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
    frame = frame[frame["created_dt"] >= pd.Timestamp("2025-08-01", tz="UTC")].copy()
    frame["period"] = np.where(
        frame["created_dt"] < pd.Timestamp("2025-12-01", tz="UTC"),
        "2025-08_to_2025-11",
        "2025-12_to_2026-03",
    )
    frame["prefix_status"] = np.where(
        frame["title"].map(classify_title).notna(), "explicit_prefix", "no_prefix"
    )
    frame["title"] = frame["title"].fillna("").str.slice(0, 500)
    frame["body"] = frame["body"].fillna("").str.slice(0, 2000)
    frame = frame[frame["title"].str.len() > 0].copy()

    sampled = []
    for _, group in frame.groupby(["agent", "period", "prefix_status"], sort=True):
        n = min(TARGET_PER_STRATUM, len(group))
        sampled.append(group.sample(n=n, random_state=SEED))
    sample = pd.concat(sampled, ignore_index=True).drop_duplicates("id")
    sample["case_id"] = sample["id"].map(stable_code)
    sample = sample.sample(frac=1.0, random_state=SEED).reset_index(drop=True)

    coder = sample[["case_id", "title", "body", "html_url"]].copy()
    coder["task_label"] = ""
    coder["confidence_1_to_5"] = ""
    coder["evidence_from_title_or_body"] = ""
    coder["notes"] = ""

    key = sample[
        [
            "case_id",
            "id",
            "agent",
            "period",
            "prefix_status",
            "repo_url",
            "classification_margin",
            "task_type",
        ]
    ].rename(columns={"task_type": "model_prediction"})
    return coder, key


if __name__ == "__main__":
    common = AnalysisConfig.from_paths(PROJECT_ROOT)
    output_dir = common.output_dir / "task_label_validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = common.output_dir / "specialization" / "task_type_predictions.parquet"
    coder, key = sample_packet(common.data_dir, predictions)
    coder.to_csv(output_dir / "coder_a_blinded.csv", index=False)
    coder.to_csv(output_dir / "coder_b_blinded.csv", index=False)
    key.to_csv(output_dir / "private_sampling_key.csv", index=False)
    strata = (
        key.groupby(["agent", "period", "prefix_status"], observed=True)
        .size()
        .rename("n")
        .reset_index()
    )
    strata.to_csv(output_dir / "sampling_summary.csv", index=False)
    metadata = {
        "dataset_revision": DATASET_REVISION,
        "seed": SEED,
        "target_per_agent_period_prefix_stratum": TARGET_PER_STRATUM,
        "sample_rows": int(len(coder)),
        "allowed_labels": ALLOWED_LABELS,
        "blinding": "Coder files exclude agent, period, prefix status, and model prediction.",
        "adjudication": "Two independent human coders; reconcile only after both files are locked.",
    }
    with (output_dir / "packet_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    print(json.dumps(metadata, indent=2))
