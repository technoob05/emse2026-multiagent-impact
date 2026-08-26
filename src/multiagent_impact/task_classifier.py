from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC
from sklearn.feature_extraction.text import TfidfVectorizer


CORE_TASKS = {"feat", "fix", "docs", "test"}


def broad_task_type(label: str) -> str:
    return label if label in CORE_TASKS else "maintenance"


def load_training_data(data_dir: Path) -> pd.DataFrame:
    pull_requests = pd.read_parquet(
        data_dir / "pull_request.parquet",
        columns=["id", "repo_url", "title", "created_at"],
    )
    labels = pd.read_parquet(
        data_dir / "pr_task_type.parquet", columns=["id", "type", "confidence"]
    ).rename(columns={"type": "task_type"})
    frame = pull_requests.merge(labels, on="id", how="inner", validate="one_to_one")
    frame["task_type"] = frame["task_type"].map(broad_task_type)
    frame["title"] = frame["title"].fillna("")
    frame["created_dt"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
    return frame


def make_classifier() -> Pipeline:
    features = FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=80_000,
                    sublinear_tf=True,
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    lowercase=True,
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=3,
                    max_features=80_000,
                    sublinear_tf=True,
                ),
            ),
        ]
    )
    return Pipeline(
        [
            ("features", features),
            (
                "classifier",
                LinearSVC(
                    C=1.0,
                    class_weight="balanced",
                    random_state=20260825,
                    max_iter=5_000,
                ),
            ),
        ]
    )


def _evaluate_split(
    frame: pd.DataFrame, train_index: np.ndarray, test_index: np.ndarray, name: str
) -> dict[str, object]:
    model = make_classifier()
    train = frame.iloc[train_index]
    test = frame.iloc[test_index]
    model.fit(train["title"], train["task_type"])
    predicted = model.predict(test["title"])
    return {
        "split": name,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "accuracy": float(accuracy_score(test["task_type"], predicted)),
        "macro_f1": float(f1_score(test["task_type"], predicted, average="macro")),
        "weighted_f1": float(
            f1_score(test["task_type"], predicted, average="weighted")
        ),
        "per_class": classification_report(
            test["task_type"], predicted, output_dict=True, zero_division=0
        ),
    }


def evaluate_classifier(frame: pd.DataFrame) -> list[dict[str, object]]:
    indices = np.arange(len(frame))
    random_train, random_test = train_test_split(
        indices,
        test_size=0.2,
        random_state=20260825,
        stratify=frame["task_type"],
    )
    group_split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=20260825)
    group_train, group_test = next(
        group_split.split(frame, frame["task_type"], groups=frame["repo_url"])
    )
    ordered = frame.sort_values(["created_dt", "id"]).index.to_numpy()
    temporal_boundary = int(len(ordered) * 0.8)
    temporal_train = ordered[:temporal_boundary]
    temporal_test = ordered[temporal_boundary:]
    return [
        _evaluate_split(frame, random_train, random_test, "random_stratified"),
        _evaluate_split(frame, group_train, group_test, "repository_disjoint"),
        _evaluate_split(frame, temporal_train, temporal_test, "temporal_holdout"),
    ]


def train_and_predict(frame: pd.DataFrame, data_dir: Path) -> tuple[Pipeline, pd.DataFrame]:
    model = make_classifier()
    model.fit(frame["title"], frame["task_type"])
    all_prs = pd.read_parquet(
        data_dir / "pull_request.parquet", columns=["id", "title"]
    )
    titles = all_prs["title"].fillna("")
    decisions = model.decision_function(titles)
    order = np.argsort(decisions, axis=1)
    top = decisions[np.arange(len(decisions)), order[:, -1]]
    runner_up = decisions[np.arange(len(decisions)), order[:, -2]]
    predictions = pd.DataFrame(
        {
            "id": all_prs["id"].to_numpy(),
            "task_type": model.classes_[order[:, -1]],
            "classification_margin": top - runner_up,
        }
    )
    return model, predictions


def run_task_classification(data_dir: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    training = load_training_data(data_dir)
    evaluations = evaluate_classifier(training)
    _, predictions = train_and_predict(training, data_dir)
    predictions.to_parquet(output_dir / "task_type_predictions.parquet", index=False)
    result = {
        "training_rows": int(len(training)),
        "classes": sorted(training["task_type"].unique().tolist()),
        "evaluations": evaluations,
        "prediction_rows": int(len(predictions)),
        "margin_quantiles": {
            str(key): float(value)
            for key, value in predictions["classification_margin"]
            .quantile([0.05, 0.25, 0.5, 0.75, 0.95])
            .items()
        },
    }
    with (output_dir / "task_classifier_evaluation.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    return result
