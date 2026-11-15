from __future__ import annotations

import numpy as np
import pandas as pd

TARGET_DEFAULT_RATE = 0.085
PURPOSE_LOGIT = {
    "Debt consolidation": 0.15,
    "Credit card": 0.10,
    "Home improvement": -0.20,
    "Auto": -0.25,
    "Medical": 0.35,
    "Other": 0.0,
}
HOME_LOGIT = {"Rent": 0.20, "Mortgage": -0.05, "Own": -0.15}


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def _calibrate_intercept(raw_logit: np.ndarray, target_rate: float) -> float:
    low, high = -15.0, 5.0
    for _ in range(60):
        mid = (low + high) / 2
        if _sigmoid(raw_logit + mid).mean() > target_rate:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def make_portfolio(row_count: int = 6000, seed: int = 42) -> pd.DataFrame:
    """Synthetic loan book; defaults are drawn from a hidden logit with a nonlinear term and noise."""
    rng = np.random.default_rng(seed)

    booked = pd.Timestamp("2023-01-01") + pd.to_timedelta(
        rng.integers(0, 1095, row_count), unit="D"
    )
    credit_score = np.clip(rng.normal(705, 62, row_count), 500, 850).round().astype(int)
    segment = np.select(
        [credit_score >= 720, credit_score >= 660], ["Prime", "Near-prime"], "Subprime"
    )
    score_gap = 705 - credit_score

    income = np.clip(rng.lognormal(np.log(72000), 0.48, row_count), 22000, 240000)
    loan_amount = np.clip(rng.lognormal(np.log(14000), 0.55, row_count), 2000, 50000)
    term = rng.choice([36, 48, 60], row_count, p=[0.45, 0.25, 0.30])
    dti = np.clip(rng.beta(2.4, 5.2, row_count) * 0.88 + score_gap / 2500, 0.04, 0.78)
    utilization = np.clip(rng.beta(2.1, 3.7, row_count) + score_gap / 900, 0.02, 0.99)
    delinquencies = np.minimum(
        rng.poisson(np.clip(0.15 + score_gap / 250, 0.05, 2.0)), 5
    )
    inquiries = np.minimum(rng.poisson(np.clip(0.9 + score_gap / 400, 0.2, 3.0)), 8)
    employment_years = np.clip(rng.gamma(2.0, 3.0, row_count), 0, 30)
    purpose = rng.choice(
        list(PURPOSE_LOGIT), row_count, p=[0.36, 0.22, 0.14, 0.12, 0.06, 0.10]
    )
    home = rng.choice(list(HOME_LOGIT), row_count, p=[0.42, 0.38, 0.20])
    state = rng.choice(
        ["CA", "TX", "FL", "NY", "IL", "GA", "AZ", "NC"],
        row_count,
        p=[0.18, 0.16, 0.13, 0.12, 0.11, 0.10, 0.10, 0.10],
    )

    loan_to_income = loan_amount / income
    raw_logit = (
        -0.016 * (credit_score - 705)
        + 2.2 * (dti - 0.30)
        + 1.2 * (utilization - 0.40)
        + 2.5 * np.maximum(utilization - 0.70, 0)
        + 2.5 * (dti - 0.30) * (utilization - 0.40)
        + 0.35 * delinquencies
        + 0.12 * inquiries
        - 0.04 * np.minimum(employment_years, 15)
        + 2.0 * (loan_to_income - 0.20)
        + np.where(term == 60, 0.45, np.where(term == 36, -0.10, 0.10))
        + pd.Series(purpose).map(PURPOSE_LOGIT).to_numpy()
        + pd.Series(home).map(HOME_LOGIT).to_numpy()
        + rng.normal(0, 0.45, row_count)
    )
    true_pd = _sigmoid(raw_logit + _calibrate_intercept(raw_logit, TARGET_DEFAULT_RATE))
    defaulted = rng.binomial(1, true_pd)

    apr = np.clip(
        6.0 + (780 - credit_score) * 0.05 + np.where(term == 60, 1.0, 0)
        + rng.normal(0, 1.1, row_count),
        4.5,
        29.9,
    )
    balance = loan_amount * rng.uniform(0.40, 1.0, row_count)

    return pd.DataFrame(
        {
            "Loan ID": [f"LN-{number:05d}" for number in range(1, row_count + 1)],
            "Booked": booked,
            "Segment": segment,
            "State": state,
            "Credit score": credit_score,
            "Annual income": income.round(0).astype(int),
            "Debt-to-income": dti,
            "Utilization": utilization,
            "Loan amount": loan_amount.round(0).astype(int),
            "Term": term,
            "Purpose": purpose,
            "Home ownership": home,
            "Employment years": employment_years.round(1),
            "Delinquencies 2y": delinquencies,
            "Inquiries 6m": inquiries,
            "Balance": balance.round(2),
            "APR": apr,
            "Defaulted": defaulted,
        }
    )
