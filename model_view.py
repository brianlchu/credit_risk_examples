from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from model import (
    MODEL_NAMES, NUMERIC, OOT_CUTOFF, ModelResult, feature_importance,
    pd_to_score, prepare_features,
)


@st.cache_data
def cached_importance(model_name: str, _result: ModelResult, _df: pd.DataFrame) -> pd.DataFrame:
    return feature_importance(_result, _df)


def card(label: str, value: str, note: str = "") -> str:
    return (
        f"<div class='metric'><div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value}</div><div class='metric-note'>{note}</div></div>"
    )


def heading(title: str, caption: str) -> None:
    st.markdown(
        f"<div class='section-heading'>{title}</div><div class='section-caption'>{caption}</div>",
        unsafe_allow_html=True,
    )


def render(
    df: pd.DataFrame,
    results: dict[str, ModelResult],
    model_name: str,
    chart_layout: Callable[..., go.Figure],
    colors: dict[str, str],
) -> None:
    result = results[model_name]
    test = df[df["Booked"] >= OOT_CUTOFF].reset_index(drop=True)
    y_test = test["Defaulted"].to_numpy()
    test_score = pd_to_score(result.test_pd)

    with st.sidebar:
        st.markdown("<div class='eyebrow' style='margin-top:24px'>Decision strategy</div>", unsafe_allow_html=True)
        cutoff = st.slider("Approval cutoff score", 500, 720, 600, step=5)

    st.markdown("<div class='eyebrow'>Credit intelligence / model lab</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-title'>How well does the model rank risk?</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='sub-title'>{model_name} trained on loans booked before {OOT_CUTOFF:%b %Y} "
        f"({len(df) - len(test):,} accounts) and tested on {len(test):,} later bookings.</div><br>",
        unsafe_allow_html=True,
    )

    metrics = result.metrics
    for column, (label, value, note) in zip(
        st.columns(4),
        [
            ("AUC", f"{metrics['AUC']:.3f}", "Out-of-time ranking power"),
            ("KS statistic", f"{metrics['KS']:.3f}", "Max separation of defaulters"),
            ("Gini", f"{metrics['Gini']:.3f}", "2 × AUC − 1"),
            ("Brier score", f"{metrics['Brier']:.3f}", f"Mean PD {metrics['Mean PD']:.1%} vs observed {metrics['Observed rate']:.1%}"),
        ],
    ):
        column.markdown(card(label, value, note), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    performance, strategy, scorer = st.tabs(["Performance", "Decision strategy", "Applicant scorer"])

    with performance:
        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            heading("ROC curve", "Out-of-time test set, both candidate models")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Random",
                                     line=dict(color=colors["line"], dash="dash")))
            palette = {MODEL_NAMES[0]: colors["green"], MODEL_NAMES[1]: colors["orange"]}
            for name, candidate in results.items():
                fig.add_trace(go.Scatter(
                    x=candidate.roc["False positive rate"], y=candidate.roc["True positive rate"],
                    mode="lines", name=f"{name} (AUC {candidate.metrics['AUC']:.3f})",
                    line=dict(color=palette[name], width=3 if name == model_name else 1.6),
                ))
            fig.update_xaxes(title="False positive rate")
            fig.update_yaxes(title="True positive rate")
            st.plotly_chart(chart_layout(fig, 320), width="stretch", config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            heading("Calibration by decile", "Average predicted PD vs observed default rate")
            calibration = result.calibration.melt(
                "Decile", ["Predicted", "Observed"], var_name="Measure", value_name="Rate"
            )
            fig = px.bar(calibration, x="Decile", y="Rate", color="Measure", barmode="group",
                         color_discrete_map={"Predicted": colors["amber"], "Observed": colors["green"]})
            fig.update_yaxes(tickformat=".0%")
            fig.update_xaxes(dtick=1, title="Risk decile (1 = lowest PD)")
            st.plotly_chart(chart_layout(fig, 320), width="stretch", config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        left, right = st.columns([1, 1], gap="medium")
        with left:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            heading("Feature importance", f"Permutation drop in AUC · {model_name}")
            importance = cached_importance(model_name, result, df)
            fig = px.bar(importance, x="AUC drop", y="Feature", orientation="h",
                         color_discrete_sequence=[colors["green"]])
            st.plotly_chart(chart_layout(fig, 340), width="stretch", config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            heading("Model comparison", "Out-of-time test metrics")
            comparison = pd.DataFrame({name: r.metrics for name, r in results.items()}).T
            st.dataframe(
                comparison.style.format(
                    {"AUC": "{:.3f}", "Gini": "{:.3f}", "KS": "{:.3f}", "Brier": "{:.4f}",
                     "Mean PD": "{:.2%}", "Observed rate": "{:.2%}"}
                ),
                width="stretch",
            )
            st.markdown(
                "<div class='insight'>Features: "
                + ", ".join(NUMERIC + ["Purpose", "Home ownership"])
                + ". Segment, state, APR, and balance are excluded from the model.</div>",
                unsafe_allow_html=True,
            )

    with strategy:
        approved = test_score >= cutoff
        approved_bad = y_test[approved].mean() if approved.any() else 0.0
        declined_bad = y_test[~approved].mean() if (~approved).any() else 0.0
        captured = y_test[~approved].sum() / max(y_test.sum(), 1)
        for column, (label, value, note) in zip(
            st.columns(4),
            [
                ("Approval rate", f"{approved.mean():.1%}", f"Score ≥ {cutoff}"),
                ("Approved default rate", f"{approved_bad:.2%}", f"Test book average {y_test.mean():.2%}"),
                ("Declined default rate", f"{declined_bad:.2%}", f"{(~approved).sum():,} declined accounts"),
                ("Defaults declined", f"{captured:.1%}", "Share of all defaults avoided"),
            ],
        ):
            column.markdown(card(label, value, note), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            heading("Score distribution", "Share of accounts by outcome, test set")
            distribution = pd.DataFrame(
                {"Score": test_score, "Outcome": np.where(y_test == 1, "Defaulted", "Repaid")}
            )
            fig = px.histogram(distribution, x="Score", color="Outcome", nbins=35, barmode="overlay",
                               histnorm="percent", opacity=0.7,
                               color_discrete_map={"Repaid": colors["green"], "Defaulted": colors["orange"]})
            fig.add_vline(x=cutoff, line_dash="dash", line_color=colors["ink"])
            fig.update_yaxes(title="% of group")
            st.plotly_chart(chart_layout(fig, 300), width="stretch", config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown("<div class='panel'>", unsafe_allow_html=True)
            heading("Cutoff trade-off", "Approval rate vs default rate among approved")
            sweep = []
            for threshold in range(500, 725, 5):
                keep = test_score >= threshold
                sweep.append((threshold, keep.mean(), y_test[keep].mean() if keep.any() else np.nan))
            sweep = pd.DataFrame(sweep, columns=["Cutoff", "Approval", "Approved default"])
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=sweep["Cutoff"], y=sweep["Approval"], name="Approval rate",
                                     line=dict(color=colors["green"], width=3)))
            fig.add_trace(go.Scatter(x=sweep["Cutoff"], y=sweep["Approved default"], name="Approved default rate",
                                     line=dict(color=colors["orange"], width=3)), secondary_y=True)
            fig.add_vline(x=cutoff, line_dash="dash", line_color=colors["ink"])
            fig.update_yaxes(tickformat=".0%", secondary_y=False)
            fig.update_yaxes(tickformat=".1%", showgrid=False, secondary_y=True)
            fig.update_xaxes(title="Cutoff score")
            st.plotly_chart(chart_layout(fig, 300), width="stretch", config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)

    with scorer:
        heading("Score a new applicant", "Adjust the inputs; the selected model scores them instantly")
        st.markdown("<br>", unsafe_allow_html=True)
        inputs, output = st.columns([1.4, 1], gap="large")
        with inputs:
            a, b, c = st.columns(3)
            credit_score = a.slider("Credit score", 500, 850, 690)
            dti = b.slider("Debt-to-income", 0.04, 0.78, 0.30, step=0.01)
            utilization = c.slider("Utilization", 0.02, 0.99, 0.40, step=0.01)
            a, b, c = st.columns(3)
            income = a.number_input("Annual income ($)", 20000, 300000, 72000, step=1000)
            loan_amount = b.number_input("Loan amount ($)", 1000, 60000, 14000, step=500)
            term = c.selectbox("Term (months)", [36, 48, 60])
            a, b, c = st.columns(3)
            delinquencies = a.slider("Delinquencies (2y)", 0, 5, 0)
            inquiries = b.slider("Inquiries (6m)", 0, 8, 1)
            employment = c.slider("Employment (years)", 0.0, 30.0, 5.0, step=0.5)
            a, b = st.columns(2)
            purpose = a.selectbox("Purpose", sorted(df["Purpose"].unique()))
            home = b.selectbox("Home ownership", sorted(df["Home ownership"].unique()))

        applicant = pd.DataFrame([{
            "Credit score": credit_score, "Annual income": income, "Loan amount": loan_amount,
            "Debt-to-income": dti, "Utilization": utilization, "Term": term,
            "Delinquencies 2y": delinquencies, "Inquiries 6m": inquiries,
            "Employment years": employment, "Purpose": purpose, "Home ownership": home,
        }])
        applicant_pd = float(result.pipeline.predict_proba(prepare_features(applicant))[:, 1][0])
        applicant_score = float(pd_to_score(applicant_pd))
        approve = applicant_score >= cutoff
        with output:
            st.markdown(card("Probability of default", f"{applicant_pd:.2%}",
                             f"{applicant_pd / df['Defaulted'].mean():.1f}× the book default rate"),
                        unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(card("Model score", f"{applicant_score:.0f}", f"Approval cutoff {cutoff}"),
                        unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                card("Decision", "Approve" if approve else "Decline",
                     f"{abs(applicant_score - cutoff):.0f} points {'above' if approve else 'below'} cutoff"),
                unsafe_allow_html=True,
            )
