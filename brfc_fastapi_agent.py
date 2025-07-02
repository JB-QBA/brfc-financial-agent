# brfc_fastapi_agent.py
# Purpose: Serve BRFC KPI and Driver Reporting Agent via FastAPI (Docker-ready)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime

app = FastAPI(title="BRFC Financial Reporting Agent")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, "*" is fine. For prod, be specific.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === CONFIG ===
GSHEET_NAME = "BRFC Financial Reporting Analysis"
BUDGET_TAB = "FY2025Budget"
ACTUALS_TAB = "AccountTransactions"
FISCAL_START = pd.Timestamp("2024-09-01")

# === MODELS ===
class ReportRequest(BaseModel):
    reporting_month: str
    action_type: str = "run_monthly_report"

# === SETUP ===
import os
import json
from google.oauth2.service_account import Credentials

def get_gsheet_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(service_account_info, scopes=scope)
    return gspread.authorize(creds)


month_order = [
    "September", "October", "November", "December", "January", "February",
    "March", "April", "May", "June", "July", "August"
]

month_map = {
    "September": "2024-09-30", "October": "2024-10-31", "November": "2024-11-30",
    "December": "2024-12-31", "January": "2025-01-31", "February": "2025-02-28",
    "March": "2025-03-31", "April": "2025-04-30", "May": "2025-05-31",
    "June": "2025-06-30", "July": "2025-07-31", "August": "2025-08-31"
}

# === ROUTES ===
@app.post("/run-report")
def run_report(request: ReportRequest):
    try:
        reporting_month = request.reporting_month
        idx = month_order.index(reporting_month) + 1
        ytd_months = month_order[:idx]
        cutoff_date = pd.to_datetime(month_map[reporting_month])

        client = get_gsheet_client()
        sheet = client.open(GSHEET_NAME)

        # === Load Budget ===
        budget_df = pd.DataFrame(sheet.worksheet(BUDGET_TAB).get_all_records())
        for col in ytd_months:
            budget_df[col] = budget_df[col].astype(str).str.replace('(', '-').str.replace(')', '').str.replace(',', '')
            budget_df[col] = pd.to_numeric(budget_df[col], errors='coerce')
        budget_df['YTD'] = budget_df[ytd_months].sum(axis=1)

        # === Load Actuals ===
        raw = sheet.worksheet(ACTUALS_TAB).get_all_values()
        actuals_df = pd.DataFrame(raw[4:], columns=raw[3])
        actuals_df['Date'] = pd.to_datetime(actuals_df['Date'], errors='coerce')
        actuals_df['Net'] = pd.to_numeric(
            actuals_df['Net'].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce')
        actuals_df['Account Name'] = actuals_df['Account Name'].str.strip()
        actuals_df = actuals_df.dropna(subset=['Date'])

        actuals_ytd = actuals_df[(actuals_df['Date'] >= FISCAL_START) & (actuals_df['Date'] <= cutoff_date)]

        # === Define account categories ===
        income_accounts = [
            "Clubhouse Sales", "Clubhouse Sales: Value in Kind", "Club Membership Revenue",
            "Sponsorship Revenue", "Events Revenue (internal)", "Facilities Revenue",
            "Sports Programs Revenue", "Visitor Sales"
        ]
        gp_cost_account = "Cost of Clubhouse Sales"
        driver_accounts = [
            "Direct Other Cost of Clubhouse Sales", "Direct Other Cost of Clubhouse: Wastage",
            "Direct Other Cost of Clubhouse: Consumables", "Direct Other Cost of Clubhouse: Events",
            "Direct Other Cost of Sports Programs", "Direct Other Cost of Facilities",
            "Direct Other Cost of Sports Events", "Direct Other Cost of Membership",
            "Direct Other Cost of Membership: Sports", "Direct Other Cost of Membership: Discounts",
            "Reception Variance", "Direct Other Cost of Sponsorship",
            "Direct Other Cost of Events (internal)", "Bank Card Fees"
        ]
        other_income_accounts = [
            "Ad Hoc Revenue", "Bank Interest Received", "Discount Received",
            "Kit Sales", "Cost of Kit Sales", "Rental Income", "Value in Kind Benefit"
        ]

        # === KPI Computation ===
        total_income_actual = actuals_ytd[actuals_ytd['Account Name'].isin(income_accounts)]['Net'].sum()
        gp_actual_cost = actuals_ytd[actuals_ytd['Account Name'] == gp_cost_account]['Net'].sum()
        driver_actual_total = actuals_ytd[actuals_ytd['Account Name'].isin(driver_accounts)]['Net'].sum()

        opex_all = actuals_ytd[~actuals_ytd['Account Name'].isin(income_accounts + [gp_cost_account] + driver_accounts)]
        other_income_total = actuals_ytd[actuals_ytd['Account Name'].isin(other_income_accounts)]['Net'].sum()
        total_opex_actual = opex_all['Net'].sum() - other_income_total

        bottom_line_actual = total_income_actual - gp_actual_cost - driver_actual_total - total_opex_actual

        total_income_budget = budget_df[budget_df['Account'].isin(income_accounts)]['YTD'].sum()
        gp_budget_cost = budget_df[budget_df['Account'] == gp_cost_account]['YTD'].sum()
        driver_budget_total = budget_df[budget_df['Account'].isin(driver_accounts)]['YTD'].sum()
        budget_opex_total = -1 * budget_df[~budget_df['Account'].isin(income_accounts + [gp_cost_account] + driver_accounts)]['YTD'].sum()

        bottom_line_budget = total_income_budget - gp_budget_cost - driver_budget_total - budget_opex_total

        # === Output ===
        return {
            "reporting_month": reporting_month,
            "total_income": {"actual": total_income_actual, "budget": total_income_budget},
            "gp_cost": {"actual": gp_actual_cost, "budget": gp_budget_cost},
            "driver_costs": {"actual": driver_actual_total, "budget": driver_budget_total},
            "operating_expenses": {"actual": total_opex_actual, "budget": budget_opex_total},
            "bottom_line": {"actual": bottom_line_actual, "budget": bottom_line_budget}
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))