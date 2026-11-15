# Northstar Credit Portfolio

A Streamlit credit-risk app powered by reproducible synthetic loan data.

- **Portfolio view**: KPIs, segment/state/date filters, a PD stress scenario, vintage trends, account-level detail, and CSV export. PDs are out-of-fold model scores.
- **Model lab**: logistic regression vs gradient boosting PD models trained on pre-2025 bookings and tested out-of-time on 2025 bookings. Shows AUC/KS/Gini/Brier, ROC, decile calibration, permutation importance, a score-cutoff decision strategy, and a single-applicant scorer.

Data generation is in `data.py`, modeling in `model.py`, and the Model lab UI in `model_view.py`. All records are mocked, and the PD and expected-loss values are illustrative, not suitable for underwriting or forecasting.

## Run

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```