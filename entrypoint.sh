#!/bin/sh
# entrypoint.sh
# Runs data profiling first, then the referral fraud-detection pipeline.
# Both read from /app/data (mounted, read-only) and write to /app/reports
# (mounted, so results land on the host machine outside the container).

set -e


echo " Step 1/2: Data Profiling"

python3 profile_data.py --input-dir data --output-dir reports/profiling

echo ""

echo " Step 2/2: Referral Pipeline & Fraud Check"

python3 referral_pipeline.py --input-dir data --output-dir reports --output-file referral_fraud_report.csv

echo ""
echo "Done. Reports available under ./reports on the host machine."
