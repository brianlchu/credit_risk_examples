from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC = [
    "Credit score",
    "Log income",
    "Debt-to-income",
    "Utilization",
    "Loan-to-income",
    "Term",
    "Delinquencies 2y",
    "Inquiries 6m",
    "Employment years",
]
CATEGORICAL = ["Purpose", "Home ownership"]
MODEL_NAMES = ["Logistic regression", "Gradient boosting"]
OOT_CUTOFF = pd.Timestamp("2025-01-01")

# Score scaling: 700 points at 30:1 good/bad odds, 50 points to double the odds.
BASE_SCORE, BASE_ODDS, PDO = 700, 30, 50


@dataclass
class ModelResult:
    name: str
    pipeline: Pipeline
    test_pd: np.ndarray
    metrics: dict[str, float]
    roc: pd.DataFrame
    calibration: pd.DataFrame


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    features = df[
        ["Credit score", "Debt-to-income", "Utilization", "Term", "Delinquencies 2y",
         "Inquiries 6m", "Employment years", "Purpose", "Home ownership"]
    ].copy()
    features["Log income"] = np.log(df["Annual income"])
    features["Loan-to-income"] = df["Loan amount"] / df["Annual income"]
    return features[NUMERIC + CATEGORICAL]


def build_pipeline(name: str) -> Pipeline:
    preprocess = ColumnTransformer(
        [
            ("num", StandardScaler(), NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    )
    if name == "Logistic regression":
        estimator = LogisticRegression(C=1.0, max_iter=1000)
    else:
        estimator = HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.06, max_iter=200,
            l2_regularization=1.0, random_state=42,
        )
    return Pipeline([("prep", preprocess), ("model", estimator)])


def ks_statistic(y_true: np.ndarray, pd_hat: np.ndarray) -> float:
    return float(ks_2samp(pd_hat[y_true == 1], pd_hat[y_true == 0]).statistic)


def calibration_table(y_true: np.ndarray, pd_hat: np.ndarray, bins: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"pd": pd_hat, "y": y_true})
    frame["Decile"] = pd.qcut(frame["pd"], bins, labels=False, duplicates="drop") + 1
    table = frame.groupby("Decile").agg(
        Accounts=("y", "size"), Predicted=("pd", "mean"), Observed=("y", "mean")
    )
    return table.reset_index()


def train_and_evaluate(df: pd.DataFrame) -> dict[str, ModelResult]:
    """Fit on pre-2025 bookings and evaluate on 2025 bookings (out-of-time)."""
    train_mask = (df["Booked"] < OOT_CUTOFF).to_numpy()
    features = prepare_features(df)
    y = df["Defaulted"].to_numpy()
    results = {}
    for name in MODEL_NAMES:
        pipeline = build_pipeline(name).fit(features[train_mask], y[train_mask])
        test_pd = pipeline.predict_proba(features[~train_mask])[:, 1]
        y_test = y[~train_mask]
        auc = roc_auc_score(y_test, test_pd)
        fpr, tpr, _ = roc_curve(y_test, test_pd)
        results[name] = ModelResult(
            name=name,
            pipeline=pipeline,
            test_pd=test_pd,
            metrics={
                "AUC": auc,
                "Gini": 2 * auc - 1,
                "KS": ks_statistic(y_test, test_pd),
                "Brier": brier_score_loss(y_test, test_pd),
                "Mean PD": float(test_pd.mean()),
                "Observed rate": float(y_test.mean()),
            },
            roc=pd.DataFrame({"False positive rate": fpr, "True positive rate": tpr}),
            calibration=calibration_table(y_test, test_pd),
        )
    return results


def out_of_fold_pd(df: pd.DataFrame, name: str) -> np.ndarray:
    """Out-of-fold PDs so portfolio scores are not inflated by in-sample fit."""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    return cross_val_predict(
        build_pipeline(name), prepare_features(df), df["Defaulted"], cv=cv, method="predict_proba"
    )[:, 1]


def feature_importance(result: ModelResult, df: pd.DataFrame) -> pd.DataFrame:
    test = df[df["Booked"] >= OOT_CUTOFF]
    importance = permutation_importance(
        result.pipeline, prepare_features(test), test["Defaulted"],
        scoring="roc_auc", n_repeats=5, random_state=42,
    )
    return (
        pd.DataFrame(
            {"Feature": NUMERIC + CATEGORICAL, "AUC drop": importance.importances_mean}
        )
        .sort_values("AUC drop")
        .reset_index(drop=True)
    )


def pd_to_score(pd_hat: np.ndarray | float) -> np.ndarray | float:
    pd_hat = np.clip(pd_hat, 1e-4, 1 - 1e-4)
    factor = PDO / np.log(2)
    offset = BASE_SCORE - factor * np.log(BASE_ODDS)
    return np.clip(offset + factor * np.log((1 - pd_hat) / pd_hat), 300, 850)
