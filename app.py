from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Northstar | Credit portfolio",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "ink": "#18211f",
    "muted": "#718078",
    "line": "#e5e9e3",
    "green": "#147d64",
    "green_light": "#dff1e9",
    "lime": "#d9ef73",
    "orange": "#df744a",
    "amber": "#e9b64d",
    "paper": "#f6f7f2",
}


@st.cache_data
def make_portfolio() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    row_count = 1800
    booked = pd.to_datetime(
        rng.choice(pd.date_range("2023-01-01", "2025-12-01", freq="MS"), row_count)
    )
    segments = rng.choice(
        ["Prime", "Near-prime", "Subprime"], row_count, p=[0.43, 0.39, 0.18]
    )
    segment_pd = pd.Series(segments).map(
        {"Prime": 0.022, "Near-prime": 0.067, "Subprime": 0.158}
    ).to_numpy()
    income = np.clip(rng.lognormal(np.log(72000), 0.48, row_count), 22000, 240000)
    dti = np.clip(rng.beta(2.4, 5.2, row_count) * 0.88, 0.04, 0.78)
    utilization = np.clip(rng.beta(2.1, 3.7, row_count), 0.02, 0.99)
    credit_score = np.clip(
        rng.normal(706, 52, row_count)
        - np.where(segments == "Subprime", 56, 0)
        - np.where(segments == "Prime", -25, 0),
        510,
        850,
    ).astype(int)
    balance = np.clip(rng.lognormal(np.log(13800), 0.62, row_count), 1500, 65000)
    apr = np.clip(
        5.8 + (850 - credit_score) * 0.075 + rng.normal(0, 1.15, row_count), 4.5, 29.9
    )
    risk_logit = (
        np.log(segment_pd / (1 - segment_pd))
        + 2.0 * (dti - 0.32)
        + 1.05 * (utilization - 0.42)
        + 0.16 * (700 - credit_score) / 50
    )
    pd_estimate = 1 / (1 + np.exp(-risk_logit))
    defaulted = rng.binomial(1, pd_estimate)
    return pd.DataFrame(
        {
            "Loan ID": [f"LN-{number:05d}" for number in range(1, row_count + 1)],
            "Booked": booked,
            "Segment": segments,
            "State": rng.choice(
                ["CA", "TX", "FL", "NY", "IL", "GA", "AZ", "NC"],
                row_count,
                p=[0.18, 0.16, 0.13, 0.12, 0.11, 0.10, 0.10, 0.10],
            ),
            "Credit score": credit_score,
            "Annual income": income.round(0).astype(int),
            "Debt-to-income": dti,
            "Utilization": utilization,
            "Balance": balance.round(2),
            "APR": apr,
            "Base PD": pd_estimate,
            "Defaulted": defaulted,
        }
    )


def money(value: float, compact: bool = False) -> str:
    if compact and abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}m"
    if compact and abs(value) >= 1_000:
        return f"${value / 1_000:.0f}k"
    return f"${value:,.0f}"


def chart_layout(fig: go.Figure, height: int = 290) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=8, t=18, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color=COLORS["muted"], size=11),
        xaxis=dict(showgrid=False, linecolor=COLORS["line"], tickfont_size=10),
        yaxis=dict(showgrid=True, gridcolor="#edf0eb", zeroline=False, tickfont_size=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font_size=10),
        hoverlabel=dict(bgcolor="#18211f", font_color="white"),
    )
    return fig


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root { --ink:#18211f; --muted:#718078; --line:#e5e9e3; --green:#147d64; --paper:#f6f7f2; }
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--ink); }
    .stApp { background:var(--paper); }
    [data-testid="stHeader"] { background:rgba(246,247,242,.94); }
    [data-testid="stSidebar"] { background:#eef1e9; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] > div { padding-top:1.35rem; }
    .block-container { max-width:1440px; padding:1.1rem 2.1rem 3rem; }
    h1,h2,h3 { font-family:'Manrope',sans-serif; color:var(--ink); letter-spacing:0; }
    .brand { display:flex; align-items:center; gap:11px; font-family:'Manrope',sans-serif; font-weight:800; font-size:17px; }
    .brand-mark { width:32px; height:32px; display:grid; place-items:center; background:#18211f; color:#d9ef73; border-radius:9px; font-weight:800; }
    .eyebrow { color:#718078; text-transform:uppercase; font-weight:700; font-size:10px; letter-spacing:1.3px; }
    .page-title { font-family:'Manrope',sans-serif; font-weight:700; font-size:30px; line-height:1.15; margin:.45rem 0 .35rem; }
    .sub-title { color:#718078; font-size:13px; }
    .metric { background:#fff; border:1px solid #e7ebe5; border-radius:7px; padding:16px 17px 14px; min-height:112px; }
    .metric-label { color:#718078; font-size:11px; font-weight:600; }
    .metric-value { font-family:'Manrope',sans-serif; color:#18211f; font-size:25px; font-weight:700; margin-top:8px; line-height:1.1; }
    .metric-note { color:#718078; font-size:10px; margin-top:7px; }
    .metric-positive { color:#147d64; font-weight:700; }
    .section-heading { font-family:'Manrope',sans-serif; font-size:15px; font-weight:700; color:#18211f; }
    .section-caption { color:#718078; font-size:11px; margin-top:2px; }
    .panel { background:#fff; border:1px solid #e7ebe5; border-radius:7px; padding:16px 17px 10px; }
    .insight { background:#e9f2e9; border-left:3px solid #147d64; border-radius:3px; padding:12px 14px; font-size:12px; color:#31443b; }
    div[data-testid="stDataFrame"] { border:1px solid #e7ebe5; border-radius:6px; }
    div[data-testid="stButton"] button { border-radius:5px; }
    hr { border-color:#e5e9e3; }
    @media (max-width:700px) { .block-container { padding: .8rem 1rem 2rem; } .page-title { font-size:25px; } .metric { min-height:100px; padding:13px; } .metric-value { font-size:22px; } }
    </style>
    """,
    unsafe_allow_html=True,
)

portfolio = make_portfolio()

with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-mark">N</div>northstar <span style="font-weight:500;color:#718078">/ risk</span></div>', unsafe_allow_html=True)
    st.markdown("<br><div class='eyebrow'>Portfolio lens</div>", unsafe_allow_html=True)
    st.caption("Adjust the view. Metrics and charts recalculate instantly.")
    selected_segments = st.multiselect(
        "Risk segment", ["Prime", "Near-prime", "Subprime"], default=["Prime", "Near-prime", "Subprime"]
    )
    selected_states = st.multiselect(
        "State", sorted(portfolio["State"].unique()), default=sorted(portfolio["State"].unique())
    )
    date_range = st.date_input(
        "Booking window", value=(date(2023, 1, 1), date(2025, 12, 31)),
        min_value=date(2023, 1, 1), max_value=date(2025, 12, 31),
    )
    st.markdown("<div class='eyebrow' style='margin-top:24px'>Stress scenario</div>", unsafe_allow_html=True)
    pd_shift = st.slider("Relative PD increase", 0, 100, 25, step=5, format="%d%%")
    lgd = st.slider("Loss given default", 20, 90, 60, step=5, format="%d%%") / 100
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Illustrative synthetic data · refreshed on app restart")

if len(date_range) == 2:
    start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
else:
    start_date, end_date = pd.Timestamp("2023-01-01"), pd.Timestamp(date_range[0])

filtered = portfolio.loc[
    portfolio["Segment"].isin(selected_segments)
    & portfolio["State"].isin(selected_states)
    & portfolio["Booked"].between(start_date, end_date)
].copy()
filtered["Scenario PD"] = np.clip(filtered["Base PD"] * (1 + pd_shift / 100), 0, 1)
filtered["Risk band"] = pd.cut(
    filtered["Base PD"], bins=[0, 0.03, 0.08, 0.15, 1],
    labels=["Low", "Moderate", "Elevated", "High"], include_lowest=True,
)

st.markdown("<div class='eyebrow'>Credit intelligence / portfolio overview</div>", unsafe_allow_html=True)
st.markdown("<div class='page-title'>Know what’s on the books.</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>A clear read on portfolio health, concentration, and downside exposure.</div>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

loan_count = len(filtered)
total_balance = filtered["Balance"].sum()
weighted_pd = np.average(filtered["Base PD"], weights=filtered["Balance"]) if loan_count else 0
expected_loss = (filtered["Balance"] * filtered["Scenario PD"] * lgd).sum() if loan_count else 0
observed_rate = filtered["Defaulted"].mean() if loan_count else 0

metric_cols = st.columns(4)
metric_data = [
    ("Active accounts", f"{loan_count:,}", "Across selected segments and states"),
    ("Outstanding balance", money(total_balance, True), f"Average exposure {money(total_balance / loan_count) if loan_count else '$0'}"),
    ("Weighted average PD", f"{weighted_pd:.2%}", f"Observed default rate {observed_rate:.2%}"),
    ("Stressed expected loss", money(expected_loss, True), f"PD +{pd_shift}% · LGD {lgd:.0%}"),
]
for column, (label, value, note) in zip(metric_cols, metric_data):
    with column:
        st.markdown(
            f"<div class='metric'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div><div class='metric-note'>{note}</div></div>",
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)
chart_left, chart_right = st.columns([1.13, 0.87], gap="medium")
with chart_left:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Risk mix by segment</div><div class='section-caption'>Account count and balance distribution</div>", unsafe_allow_html=True)
    if loan_count:
        risk_order = ["Low", "Moderate", "Elevated", "High"]
        risk_colors = {"Low": "#8abf9e", "Moderate": "#d9ef73", "Elevated": "#e9b64d", "High": "#df744a"}
        segment_mix = filtered.groupby(["Segment", "Risk band"], observed=False).size().reset_index(name="Accounts")
        fig = px.bar(segment_mix, x="Segment", y="Accounts", color="Risk band", barmode="stack",
                     category_orders={"Risk band": risk_order}, color_discrete_map=risk_colors)
        st.plotly_chart(chart_layout(fig, 280), width="stretch", config={"displayModeBar": False})
    else:
        st.info("No accounts match the selected filters.")
    st.markdown("</div>", unsafe_allow_html=True)

with chart_right:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Exposure by risk band</div><div class='section-caption'>Share of outstanding balance</div>", unsafe_allow_html=True)
    if loan_count:
        exposure = filtered.groupby("Risk band", observed=False)["Balance"].sum().reindex(risk_order).fillna(0).reset_index()
        fig = px.pie(exposure, values="Balance", names="Risk band", hole=0.68,
                     color="Risk band", color_discrete_map=risk_colors)
        fig.update_traces(textinfo="percent", textposition="outside", marker=dict(line=dict(color="white", width=2)))
        fig.add_annotation(text=money(total_balance, True), x=0.5, y=0.52, showarrow=False,
                           font=dict(family="Manrope", size=17, color=COLORS["ink"]))
        st.plotly_chart(chart_layout(fig, 280), width="stretch", config={"displayModeBar": False})
    else:
        st.info("No accounts match the selected filters.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
vintage_col, insight_col = st.columns([1.5, 0.7], gap="medium")
with vintage_col:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Vintage performance</div><div class='section-caption'>Observed default rate by booking quarter</div>", unsafe_allow_html=True)
    if loan_count:
        vintage = filtered.assign(Quarter=filtered["Booked"].dt.to_period("Q").astype(str)).groupby("Quarter", as_index=False).agg(
            **{"Observed default": ("Defaulted", "mean"), "Portfolio PD": ("Base PD", "mean")}
        )
        vintage_long = vintage.melt("Quarter", var_name="Measure", value_name="Rate")
        fig = px.line(vintage_long, x="Quarter", y="Rate", color="Measure", markers=True,
                      color_discrete_map={"Observed default": COLORS["green"], "Portfolio PD": COLORS["orange"]})
        fig.update_yaxes(tickformat=".0%")
        fig.update_traces(line_width=2.5, marker_size=6)
        st.plotly_chart(chart_layout(fig, 245), width="stretch", config={"displayModeBar": False})
    else:
        st.info("No accounts match the selected filters.")
    st.markdown("</div>", unsafe_allow_html=True)

with insight_col:
    st.markdown("<div class='panel' style='height:100%'>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Scenario readout</div><div class='section-caption'>Loss sensitivity at current settings</div><br>", unsafe_allow_html=True)
    stressed_pd = np.average(filtered["Scenario PD"], weights=filtered["Balance"]) if loan_count else 0
    loss_delta = expected_loss - (filtered["Balance"] * filtered["Base PD"] * lgd).sum() if loan_count else 0
    st.markdown(
        f"<div class='metric' style='background:#f6f7f2;min-height:90px'><div class='metric-label'>Stressed weighted PD</div><div class='metric-value'>{stressed_pd:.2%}</div><div class='metric-note'>Base case {weighted_pd:.2%}</div></div><br>"
        f"<div class='metric' style='background:#f6f7f2;min-height:90px'><div class='metric-label'>Incremental expected loss</div><div class='metric-value' style='font-size:23px'>{money(loss_delta, True)}</div><div class='metric-note'>Versus base case at {lgd:.0%} LGD</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("<div class='section-heading'>Account-level view</div><div class='section-caption'>Filtered accounts sorted by estimated probability of default</div>", unsafe_allow_html=True)
if loan_count:
    display = filtered.sort_values("Base PD", ascending=False).copy()
    display["Booked"] = display["Booked"].dt.strftime("%b %Y")
    display["Annual income"] = display["Annual income"].map(money)
    display["Balance"] = display["Balance"].map(money)
    display["Debt-to-income"] = display["Debt-to-income"].map(lambda value: f"{value:.0%}")
    display["Utilization"] = display["Utilization"].map(lambda value: f"{value:.0%}")
    display["APR"] = display["APR"].map(lambda value: f"{value:.2f}%")
    display["Base PD"] = display["Base PD"].map(lambda value: f"{value:.2%}")
    display["Scenario PD"] = display["Scenario PD"].map(lambda value: f"{value:.2%}")
    display["Defaulted"] = display["Defaulted"].map({1: "Yes", 0: "No"})
    st.dataframe(
        display[["Loan ID", "Booked", "Segment", "State", "Credit score", "Annual income", "Debt-to-income", "Utilization", "Balance", "APR", "Base PD", "Scenario PD", "Defaulted"]],
        width="stretch", hide_index=True, height=355,
    )
    st.download_button(
        "Download filtered accounts as CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="northstar_credit_portfolio.csv", mime="text/csv",
    )
else:
    st.info("No accounts match the selected filters. Expand the date window or select additional segments or states.")

st.markdown("<br><hr>", unsafe_allow_html=True)
st.markdown(
    "<div class='insight'><b>Illustrative analysis only.</b> This app uses deterministic synthetic records for demonstration. PDs, defaults, and expected-loss calculations are not a validated model, credit decision, or forecast.</div>",
    unsafe_allow_html=True,
)