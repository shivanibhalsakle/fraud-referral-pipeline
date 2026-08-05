"""

This script:
    1. Loads the 7 raw referral-program CSV tables.
    2. Cleans them (literal "null" strings -> NaN, data type fixes, string trimming).
    3. Processes/joins them into a single referral-level dataset, converting all UTC timestamps to the appropriate local time zone.
    4. Applies the business rules from the take-home spec to flag each referral reward as valid / invalid (`is_business_logic_valid`).
    5. Writes the final report as a CSV file (one row per referral, 46 rows for the provided sample dataset).
"""

import argparse
import os
import re

import pandas as pd
import numpy as np

pd.set_option("mode.chained_assignment", None)

NULL_LITERALS = {"null", "none", "nan", "", "n/a", "na"}


# --------------------------------------------------------------------------- #
# 1. Data Loading
# --------------------------------------------------------------------------- #
def load_data(input_dir: str) -> dict:
    """Load all raw CSV tables into a dict of DataFrames keyed by table name."""
    files = {
        "user_referrals": "user_referrals.csv",
        "user_referral_logs": "user_referral_logs.csv",
        "user_logs": "user_logs.csv",
        "user_referral_statuses": "user_referral_statuses.csv",
        "referral_rewards": "referral_rewards.csv",
        "paid_transactions": "paid_transactions.csv",
        "lead_logs": "lead_log.csv",
    }

    dataframes = {}
    for table_name, filename in files.items():
        path = os.path.join(input_dir, filename)
        dataframes[table_name] = pd.read_csv(path, dtype=str)
        print(f"Loaded {table_name}: {dataframes[table_name].shape[0]} rows")

    return dataframes


# --------------------------------------------------------------------------- #
# 2. Data Cleaning
# --------------------------------------------------------------------------- #
def clean_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """Replace literal 'null'/'none'/'' strings with real NaN across all columns."""
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].apply(
            lambda x: np.nan if isinstance(x, str) and x.strip().lower() in NULL_LITERALS else x
        )
    return df


def parse_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().map({"TRUE": True, "FALSE": False}).fillna(False)


def parse_reward_days(reward_value: str):
    """Extract the numeric day count out of strings like '10 days' -> 10."""
    if pd.isna(reward_value):
        return np.nan
    match = re.search(r"(\d+)", str(reward_value))
    return int(match.group(1)) if match else np.nan


def clean_all_tables(raw: dict) -> dict:
    """Apply null-cleaning and basic dtype fixes to every raw table."""
    cleaned = {name: clean_nulls(df) for name, df in raw.items()}

    # ---- user_referrals ----
    ur = cleaned["user_referrals"]
    ur["referral_at"] = pd.to_datetime(ur["referral_at"], utc=True, errors="coerce")
    ur["updated_at"] = pd.to_datetime(ur["updated_at"], utc=True, errors="coerce")
    cleaned["user_referrals"] = ur

    # ---- user_referral_logs ----
    url = cleaned["user_referral_logs"]
    url["created_at"] = pd.to_datetime(url["created_at"], utc=True, errors="coerce")
    url["is_reward_granted"] = parse_bool(url["is_reward_granted"])
    cleaned["user_referral_logs"] = url

    # ---- user_logs (de-duplicate identical repeated snapshots) ----
    ul = cleaned["user_logs"]
    ul["membership_expired_date"] = pd.to_datetime(ul["membership_expired_date"], errors="coerce")
    ul["is_deleted"] = ul["is_deleted"].astype(str).str.strip().str.lower().map({"true": True, "false": False}).fillna(False)
    ul["id"] = pd.to_numeric(ul["id"], errors="coerce")
    # Keep the most recent log row (highest id) per user_id to avoid join fan-out
    ul = ul.sort_values("id").drop_duplicates(subset=["user_id"], keep="last")
    cleaned["user_logs"] = ul

    # ---- user_referral_statuses ----
    urs = cleaned["user_referral_statuses"]
    cleaned["user_referral_statuses"] = urs

    # ---- referral_rewards ----
    rr = cleaned["referral_rewards"]
    rr["num_reward_days"] = rr["reward_value"].apply(parse_reward_days)
    cleaned["referral_rewards"] = rr

    # ---- paid_transactions ----
    pt = cleaned["paid_transactions"]
    pt["transaction_at"] = pd.to_datetime(pt["transaction_at"], utc=True, errors="coerce")
    pt["transaction_status"] = pt["transaction_status"].str.strip().str.title()
    pt["transaction_type"] = pt["transaction_type"].str.strip().str.title()
    cleaned["paid_transactions"] = pt

    # ---- lead_logs ----
    ll = cleaned["lead_logs"]
    ll["created_at"] = pd.to_datetime(ll["created_at"], utc=True, errors="coerce")
    cleaned["lead_logs"] = ll

    return cleaned


# --------------------------------------------------------------------------- #
# 3. Data Processing (joins, timezone conversion, feature engineering)
# --------------------------------------------------------------------------- #
def initcap(series: pd.Series) -> pd.Series:
    """Title-case a string Series, leaving NaN untouched."""
    return series.apply(lambda x: str(x).strip().title() if pd.notna(x) else x)


def to_local_time(utc_series: pd.Series, tz_series: pd.Series) -> pd.Series:
    """Convert a UTC timestamp series to local time using a per-row timezone string."""
    result = []
    for ts, tz in zip(utc_series, tz_series):
        if pd.isna(ts):
            result.append(pd.NaT)
            continue
        if pd.isna(tz):
            result.append(ts.tz_localize(None))  # keep as naive UTC if tz unknown
            continue
        try:
            result.append(ts.tz_convert(tz).tz_localize(None))
        except Exception:
            result.append(ts.tz_localize(None))
    return pd.Series(result, index=utc_series.index)


def build_referral_report(cleaned: dict) -> pd.DataFrame:
    ur = cleaned["user_referrals"].copy()
    url = cleaned["user_referral_logs"].copy()
    ul = cleaned["user_logs"].copy()
    urs = cleaned["user_referral_statuses"].copy()
    rr = cleaned["referral_rewards"].copy()
    pt = cleaned["paid_transactions"].copy()
    ll = cleaned["lead_logs"].copy()

    # ---- 3a. Latest reward-log entry per referral (avoid fan-out / duplicates) ----
    url_sorted = url.sort_values("created_at")
    latest_log = url_sorted.drop_duplicates(subset=["user_referral_id"], keep="last")
    latest_log = latest_log.rename(
        columns={
            "user_referral_id": "referral_id",
            "created_at": "reward_log_at",
        }
    )[["referral_id", "reward_log_at", "is_reward_granted"]]

    df = ur.merge(latest_log, on="referral_id", how="left")
    df["is_reward_granted"] = df["is_reward_granted"].fillna(False)
    # reward_granted_at is only meaningful when the reward was actually granted
    df["reward_granted_at"] = np.where(df["is_reward_granted"], df["reward_log_at"], pd.NaT)
    df["reward_granted_at"] = pd.to_datetime(df["reward_granted_at"], utc=True, errors="coerce")

    # ---- 3b. Referral status description ----
    urs_small = urs.rename(columns={"id": "user_referral_status_id", "description": "referral_status"})
    df = df.merge(urs_small[["user_referral_status_id", "referral_status"]], on="user_referral_status_id", how="left")

    # ---- 3c. Reward days ----
    rr_small = rr.rename(columns={"id": "referral_reward_id"})
    df = df.merge(rr_small[["referral_reward_id", "num_reward_days"]], on="referral_reward_id", how="left")

    # ---- 3d. Referrer info (dedup'd user_logs) ----
    referrer_info = ul.rename(
        columns={
            "user_id": "referrer_id",
            "name": "referrer_name",
            "phone_number": "referrer_phone_number",
            "homeclub": "referrer_homeclub",
            "timezone_homeclub": "referrer_timezone",
            "membership_expired_date": "referrer_membership_expired_date",
            "is_deleted": "referrer_is_deleted",
        }
    )[
        [
            "referrer_id",
            "referrer_name",
            "referrer_phone_number",
            "referrer_homeclub",
            "referrer_timezone",
            "referrer_membership_expired_date",
            "referrer_is_deleted",
        ]
    ]
    df = df.merge(referrer_info, on="referrer_id", how="left")

    # ---- 3e. Transaction info ----
    pt_small = pt.rename(columns={"transaction_id": "transaction_id"})
    df = df.merge(pt_small, on="transaction_id", how="left", suffixes=("", "_txn"))

    # ---- 3f. Lead source category (only relevant when referral_source == 'Lead') ----
    ll_small = ll.rename(columns={"lead_id": "referee_id", "source_category": "lead_source_category"})
    ll_small = ll_small.sort_values("created_at").drop_duplicates(subset=["referee_id"], keep="last")
    df = df.merge(ll_small[["referee_id", "lead_source_category"]], on="referee_id", how="left")

    # ---- 3g. referral_source_category business rule ----
    def source_category(row):
        if row["referral_source"] == "User Sign Up":
            return "Online"
        if row["referral_source"] == "Draft Transaction":
            return "Offline"
        if row["referral_source"] == "Lead":
            return row["lead_source_category"]
        return np.nan

    df["referral_source_category"] = df.apply(source_category, axis=1)

    # ---- 3h. Time zone conversion (UTC -> local) ----
    # referral-level system events use the referrer's home-club timezone
    df["referral_at_local"] = to_local_time(df["referral_at"], df["referrer_timezone"])
    df["updated_at_local"] = to_local_time(df["updated_at"], df["referrer_timezone"])
    df["reward_granted_at_local"] = to_local_time(df["reward_granted_at"], df["referrer_timezone"])
    # transaction events use the transaction's own timezone
    df["transaction_at_local"] = to_local_time(df["transaction_at"], df["timezone_transaction"])

    # ---- 3i. String adjustment: Initcap everywhere except club/location names ----
    df["referrer_name"] = initcap(df["referrer_name"])
    df["referee_name"] = initcap(df["referee_name"])
    df["referral_status"] = initcap(df["referral_status"])
    df["referral_source"] = initcap(df["referral_source"])
    df["referral_source_category"] = initcap(df["referral_source_category"])
    df["transaction_status"] = initcap(df["transaction_status"])
    df["transaction_type"] = initcap(df["transaction_type"])
    # club / location fields are intentionally left as-is (not initcap'd)
    # e.g. referrer_homeclub, transaction_location

    return df


# --------------------------------------------------------------------------- #
# 4. Business logic / fraud detection
# --------------------------------------------------------------------------- #
def apply_business_logic(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    has_reward_value = df["num_reward_days"].notna() & (df["num_reward_days"] > 0)
    no_reward_value = ~has_reward_value
    has_txn_id = df["transaction_id"].notna()
    no_txn_id = ~has_txn_id
    is_berhasil = df["referral_status"] == "Berhasil"
    is_pending_or_failed = df["referral_status"].isin(["Menunggu", "Tidak Berhasil"])
    txn_paid = df["transaction_status"] == "Paid"
    txn_new = df["transaction_type"] == "New"
    txn_after_referral = df["transaction_at"] > df["referral_at"]
    txn_before_referral = df["transaction_at"] < df["referral_at"]
    same_month = (df["transaction_at"].dt.to_period("M") == df["referral_at"].dt.to_period("M"))
    membership_ref_date = df["transaction_at"].fillna(df["referral_at"])
    membership_not_expired = df["referrer_membership_expired_date"] > membership_ref_date.dt.tz_localize(None)
    referrer_not_deleted = df["referrer_is_deleted"] == False  # noqa: E712
    reward_granted = df["is_reward_granted"] == True  # noqa: E712

    # ----- Valid conditions -----
    valid_condition_1 = (
        has_reward_value
        & is_berhasil
        & has_txn_id
        & txn_paid
        & txn_new
        & txn_after_referral
        & same_month
        & membership_not_expired
        & referrer_not_deleted
        & reward_granted
    )
    valid_condition_2 = is_pending_or_failed & no_reward_value

    meets_valid_condition = valid_condition_1 | valid_condition_2

    # ----- Invalid conditions -----
    # NOTE: the spec's "valid condition 2" (pending/failed status + no reward
    # value) and "invalid condition 3" (no reward value but a PAID transaction
    # exists after the referral) can both technically match the same row -
    # e.g. a referral marked "Tidak Berhasil" that nonetheless has a paid
    # transaction linked to it afterwards. That combination is itself a red
    # flag (a transaction shouldn't exist/succeed against a failed referral),
    # so invalid conditions take precedence over the valid conditions whenever
    # both match. This is one of the "additional invalid business logic"
    # patterns called out as a plus in the spec.
    invalid_condition_1 = has_reward_value & ~is_berhasil
    invalid_condition_2 = has_reward_value & no_txn_id
    invalid_condition_3 = no_reward_value & has_txn_id & txn_paid & txn_after_referral
    invalid_condition_4 = is_berhasil & no_reward_value
    invalid_condition_5 = txn_before_referral.fillna(False)

    meets_invalid_condition = (
        invalid_condition_1
        | invalid_condition_2
        | invalid_condition_3
        | invalid_condition_4
        | invalid_condition_5
    ).fillna(False)

    is_valid = meets_valid_condition.fillna(False) & ~meets_invalid_condition

    df["is_business_logic_valid"] = is_valid.fillna(False)

    # Extra diagnostic column (not required by spec, but useful for reviewers /
    # "if you found any invalid business logic is a plus")
    reasons = []
    for i in df.index:
        row_reasons = []
        if invalid_condition_1[i]:
            row_reasons.append("reward>0 but status != Berhasil")
        if invalid_condition_2[i]:
            row_reasons.append("reward>0 but no transaction_id")
        if invalid_condition_3[i]:
            row_reasons.append("no reward value but has PAID transaction after referral")
        if invalid_condition_4[i]:
            row_reasons.append("status Berhasil but reward value null/0")
        if invalid_condition_5[i]:
            row_reasons.append("transaction occurred before referral was created")
        if not row_reasons and not df.loc[i, "is_business_logic_valid"]:
            row_reasons.append("does not meet any explicit valid condition (e.g. reward not yet granted)")
        reasons.append("; ".join(row_reasons))
    df["fraud_check_notes"] = reasons

    return df


# --------------------------------------------------------------------------- #
# 5. Output
# --------------------------------------------------------------------------- #
FINAL_COLUMNS = [
    "referral_details_id",
    "referral_id",
    "referral_source",
    "referral_source_category",
    "referral_at",
    "referrer_id",
    "referrer_name",
    "referrer_phone_number",
    "referrer_homeclub",
    "referee_id",
    "referee_name",
    "referee_phone",
    "referral_status",
    "num_reward_days",
    "transaction_id",
    "transaction_status",
    "transaction_at",
    "transaction_location",
    "transaction_type",
    "updated_at",
    "reward_granted_at",
    "is_business_logic_valid",
    "fraud_check_notes",
]


def finalize_report(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["referral_details_id"] = range(101, 101 + len(df))

    df["referral_at"] = df["referral_at_local"]
    df["updated_at"] = df["updated_at_local"]
    df["transaction_at"] = df["transaction_at_local"]
    df["reward_granted_at"] = df["reward_granted_at_local"]

    out = df[FINAL_COLUMNS].copy()

    # ---- Handling nulls: fill remaining nulls with explicit, documented placeholders ----
    string_cols = [
        "referral_id", "referral_source", "referral_source_category", "referrer_id",
        "referrer_name", "referrer_phone_number", "referrer_homeclub", "referee_id",
        "referee_name", "referee_phone", "referral_status", "transaction_id",
        "transaction_status", "transaction_location", "transaction_type", "fraud_check_notes",
    ]
    for col in string_cols:
        out[col] = out[col].fillna("N/A")

    out["num_reward_days"] = out["num_reward_days"].fillna(0).astype(int)
    out["is_business_logic_valid"] = out["is_business_logic_valid"].fillna(False).astype(bool)

    for col in ["referral_at", "transaction_at", "updated_at", "reward_granted_at"]:
        out[col] = pd.to_datetime(out[col], errors="coerce")

    return out


def main():
    parser = argparse.ArgumentParser(description="Springer Capital referral pipeline & fraud check.")
    parser.add_argument("--input-dir", default="data", help="Folder containing the raw CSV files.")
    parser.add_argument("--output-dir", default="reports", help="Folder to write the output report to.")
    parser.add_argument("--output-file", default="referral_fraud_report.csv", help="Output CSV filename.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("=== 1. Loading data ===")
    raw = load_data(args.input_dir)

    print("\n=== 2. Cleaning data ===")
    cleaned = clean_all_tables(raw)

    print("\n=== 3. Processing & joining data ===")
    processed = build_referral_report(cleaned)

    print("\n=== 4. Applying fraud-detection business logic ===")
    flagged = apply_business_logic(processed)

    print("\n=== 5. Finalizing & writing report ===")
    report = finalize_report(flagged)

    output_path = os.path.join(args.output_dir, args.output_file)
    report.to_csv(output_path, index=False)

    print(f"\nReport written to: {output_path}")
    print(f"Row count: {len(report)} (expected 46)")
    print(f"Valid referrals: {int(report['is_business_logic_valid'].sum())}")
    print(f"Invalid referrals: {int((~report['is_business_logic_valid']).sum())}")


if __name__ == "__main__":
    main()
