"""Test whether an external actionability label transfers across review sources.

This is a fail-closed exploratory gate.  It never scores AIDev text unless the
external classifier clears every leave-one-source-out threshold.  Raw comment
text remains inside the third-party archive and is not written to outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import make_pipeline


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / "external_data" / "downloads" / "zenodo-19562450" / "AIReviewActionAnalysis.zip"
DEFAULT_OUTPUT = ROOT / "outputs" / "external_validation" / "actionability_transfer_probe"
BASE = "AIReviewActionAnalysis(Zenodo)/llm_analysis/"
INPUT_MEMBER = BASE + "input/reviews(llm_input)(consider_path).csv"
LABEL_MEMBER = (
    BASE
    + "output/reviews(llm_input)(consider_path)/"
    + "Suggestion_openai-gpt-4.1_p=3.12(1).csv"
)
MIN_SOURCE_AUC = 0.70
MIN_SOURCE_BALANCED_ACCURACY = 0.60


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_actionability(text: str) -> int:
    if "Classification: Contain Valid Issues Or Suggestions" in text:
        return 1
    if (
        "Classification: Only Contain General Issues Or Suggestions" in text
        or "Classification: Not Contain Any Issues Or Suggestions" in text
    ):
        return 0
    raise ValueError("Unrecognized external actionability label")


def load_external_labels(archive: Path) -> pd.DataFrame:
    with zipfile.ZipFile(archive) as bundle:
        comments = pd.read_csv(
            bundle.open(INPUT_MEMBER),
            usecols=["Comment_ID", "Body", "Source"],
        )
        labels = pd.read_csv(
            bundle.open(LABEL_MEMBER),
            usecols=["Comment_URL", "GPT_Output"],
        )
    frame = comments.merge(
        labels,
        left_on="Comment_ID",
        right_on="Comment_URL",
        how="inner",
        validate="1:1",
    )
    if len(frame) != len(comments) or len(frame) != len(labels):
        raise AssertionError("External comment and label rows do not reconcile")
    if frame[["Body", "Source", "GPT_Output"]].isna().any().any():
        raise AssertionError("External transfer fields contain null values")
    frame["actionable"] = frame["GPT_Output"].map(parse_actionability)
    return frame


def evaluate(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for source in sorted(frame["Source"].unique()):
        test = frame["Source"].eq(source)
        train = ~test
        y_test = frame.loc[test, "actionable"]
        if y_test.nunique() != 2:
            raise AssertionError(f"Held-out source has one label class: {source}")
        model = make_pipeline(
            TfidfVectorizer(
                ngram_range=(1, 2),
                min_df=3,
                max_df=0.98,
                max_features=50_000,
                strip_accents="unicode",
                sublinear_tf=True,
            ),
            LogisticRegression(
                C=2.0,
                class_weight="balanced",
                max_iter=1_000,
                random_state=20260826,
            ),
        )
        model.fit(frame.loc[train, "Body"], frame.loc[train, "actionable"])
        probability = model.predict_proba(frame.loc[test, "Body"])[:, 1]
        predicted = probability >= 0.5
        rows.append(
            {
                "held_out_source": source,
                "rows": int(test.sum()),
                "positive_share": float(y_test.mean()),
                "roc_auc": float(roc_auc_score(y_test, probability)),
                "balanced_accuracy_at_0_5": float(balanced_accuracy_score(y_test, predicted)),
                "precision_at_0_5": float(precision_score(y_test, predicted, zero_division=0)),
                "recall_at_0_5": float(recall_score(y_test, predicted, zero_division=0)),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.archive.is_file():
        raise FileNotFoundError(args.archive)
    frame = load_external_labels(args.archive)
    metrics = evaluate(frame)
    passed = bool(
        (metrics["roc_auc"] >= MIN_SOURCE_AUC).all()
        and (metrics["balanced_accuracy_at_0_5"] >= MIN_SOURCE_BALANCED_ACCURACY).all()
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.output_dir / "leave_one_source_out.csv", index=False)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Does AI Code Review Lead to Code Changes? online appendix",
        "source_record": "https://zenodo.org/records/19562450",
        "source_license": "CC-BY-4.0",
        "archive_sha256": sha256_file(args.archive),
        "rows": len(frame),
        "sources": int(frame["Source"].nunique()),
        "positive_share": float(frame["actionable"].mean()),
        "gate": {
            "minimum_each_source_roc_auc": MIN_SOURCE_AUC,
            "minimum_each_source_balanced_accuracy": MIN_SOURCE_BALANCED_ACCURACY,
            "passed": passed,
        },
        "aidev_scoring_performed": False,
        "reason": (
            "All transfer gates passed; AIDev scoring remains a separate predeclared step."
            if passed
            else "At least one held-out source failed; the proxy is rejected and AIDev text is not scored."
        ),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    weakest_auc = metrics.loc[metrics["roc_auc"].idxmin()]
    weakest_bal = metrics.loc[metrics["balanced_accuracy_at_0_5"].idxmin()]
    readme = f"""# External actionability transfer gate

The external package supplies LLM-derived labels for {len(frame):,} review
comments from {frame['Source'].nunique()} sources.  A word n-gram classifier was
trained four sources at a time and tested on the fifth source.

The gate **{'passed' if passed else 'failed'}**.  The weakest held-out ROC AUC
was {weakest_auc['roc_auc']:.3f} for `{weakest_auc['held_out_source']}`; the
weakest balanced accuracy at the fixed 0.5 threshold was
{weakest_bal['balanced_accuracy_at_0_5']:.3f} for
`{weakest_bal['held_out_source']}`.  Because every source must clear both
thresholds, the model was not applied to AIDev.

This is a construct-transfer falsification, not evidence about review quality,
semantic resolution, or causal impact.  No raw comment text is exported.
"""
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(metrics.to_string(index=False))
    print(f"transfer_gate_passed={passed}; aidev_scoring_performed=False")


if __name__ == "__main__":
    main()
