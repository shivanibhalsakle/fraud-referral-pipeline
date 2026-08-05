# Springer Capital — Referral Program Data Pipeline & Fraud Check

Profiles the referral-program source data, builds a single referral-level report, and flags each referral reward as valid or invalid per the business rules in the take-home spec.

## Repository layout
.
 data/                          # raw source CSVs (7 tables)
 reports/                       # generated output (created when you run the pipeline)
  referral_fraud_report.csv  # final report (one row per referral)
  profiling/                 # per-table data profiling results
 documentation/
  data_dictionary.xlsx       # business-facing data dictionary for the output report
 referral_pipeline.py           # main pipeline: load -> clean -> process -> flag -> output
 profile_data.py                # data profiling script (run against the raw tables)
 build_data_dictionary.py       # one-off script that generated      
 
documentation/data_dictionary.xlsx
 requirements.txt
 Dockerfile
 entrypoint.sh                  # runs profiling then the pipeline inside the container
 README.md
```

## Approach

- Tooling: Python + Pandas — the dataset is small (46 referrals), so Pandas keeps things readable; the same logic ports to PySpark/SparkSQL for larger volumes without changing the business rules.
- Grain: one row per `user_referrals` record (46 rows for the sample data).
- Joins: `user_logs` and `lead_logs` contain duplicate rows in the raw data, so both are de-duplicated before joining to avoid row fan-out.
- Time zones: raw timestamps are UTC. Referral-level events (`referral_at`, `updated_at`, `reward_granted_at`) convert to the referrer's home-club time zone; `transaction_at` converts using the transaction's own time zone.
- String formatting: Initcap applied to names, statuses, and other free text, except club/location names (`referrer_homeclub`, `transaction_location`).
- Nulls: literal `"null"` strings are cleaned to real nulls first. Remaining nulls in the final report become explicit placeholders (`"N/A"` for text, `0` for reward days) rather than dropped rows, since all 46 referrals must stay in the report.
- Fraud flag (`is_business_logic_valid`): derived from the spec's valid/invalid conditions. Where a row could satisfy both (e.g. a failed referral with a paid transaction still linked to it), the invalid condition wins — this is intentional and noted in the script comments as one of the "additional invalid patterns" the exercise invites you to find.
- Full reasoning for each decision is documented as comments in `referral_pipeline.py`.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python3 profile_data.py --input-dir data --output-dir reports/profiling
python3 referral_pipeline.py --input-dir data --output-dir reports --output-file referral_fraud_report.csv
```

Output: `reports/profiling/data_profiling_report.xlsx` (+ one CSV per table) and `reports/referral_fraud_report.csv` (46 rows, includes `is_business_logic_valid`).

## Running with Docker

Input and output live outside the container via mounted volumes.

Build:

```bash
docker build -t springer-referral-pipeline .
```

Run:

```bash
docker run --rm \
  -v "$(pwd)/data:/app/data:ro" \
  -v "$(pwd)/reports:/app/reports" \
  springer-referral-pipeline
```

On Windows PowerShell, replace `$(pwd)` with `${PWD}`. Results land in your local `./reports` folder.

## Data profiling

`profile_data.py` reports, per column of every raw table: data type, row count, null count/percentage, distinct value count, min/max, and the top 3 most frequent values — as individual CSVs and one consolidated workbook, `reports/profiling/data_profiling_report.xlsx`.

## Documentation

`documentation/data_dictionary.xlsx` defines every output column for non-technical users (e.g. a Marketing Manager), with a "How to read this report" tab. The pipeline script itself is commented throughout to explain each step.

## Credentials / cloud storage

This pipeline reads and writes local files only — no cloud storage, no credentials needed. If you extend it to upload the report to cloud storage (S3, GCS, etc.), load credentials from environment variables (e.g. `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) passed at runtime via `docker run -e VAR=value` or a `.env` file excluded from version control — never hard-code them in the script.
