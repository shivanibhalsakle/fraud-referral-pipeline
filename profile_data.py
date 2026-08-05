"""

For every raw source table (CSV file) this script computes:
    - data type (as inferred by pandas)
    - row count
    - null count / null percentage
    - distinct value count
    - min / max value (for numeric & datetime-like columns)
    - a handful of most frequent values (helps spot data-quality issues)

"""

import argparse
import os
import glob

import pandas as pd


def infer_min_max(series: pd.Series):
    """Best-effort min/max for a column, tolerant of mixed/text data."""
    non_null = series.dropna()
    if non_null.empty:
        return None, None

    # Try numeric first
    numeric = pd.to_numeric(non_null, errors="coerce")
    if numeric.notna().mean() > 0.8:  # mostly numeric
        return numeric.min(), numeric.max()

    # Try datetime
    dt = pd.to_datetime(non_null, errors="coerce", utc=True)
    if dt.notna().mean() > 0.8:  # mostly datetime
        # Strip timezone so downstream Excel export doesn't choke on tz-aware values
        return dt.min().tz_localize(None), dt.max().tz_localize(None)

    # Fall back to plain string min/max (lexicographic)
    try:
        return non_null.astype(str).min(), non_null.astype(str).max()
    except Exception:
        return None, None


def profile_table(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Build a profiling report (one row per column) for a single DataFrame."""
    rows = []
    total_rows = len(df)

    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        # Treat literal string "null"/"NULL"/"" as nulls too, common in raw CSV exports
        literal_nulls = series.astype(str).str.strip().str.lower().isin(["null", "none", ""]).sum()
        effective_nulls = max(null_count, int(literal_nulls))

        distinct_count = int(series.nunique(dropna=True))
        min_val, max_val = infer_min_max(series)

        top_values = (
            series.dropna().astype(str).value_counts().head(3).to_dict()
        )

        rows.append(
            {
                "table_name": table_name,
                "column_name": col,
                "data_type": str(series.dtype),
                "row_count": total_rows,
                "null_count": effective_nulls,
                "null_percentage": round((effective_nulls / total_rows) * 100, 2) if total_rows else 0,
                "distinct_value_count": distinct_count,
                "min_value": min_val,
                "max_value": max_val,
                "top_3_values": top_values,
            }
        )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Profile all CSV source tables.")
    parser.add_argument("--input-dir", default="data", help="Folder containing the raw CSV files.")
    parser.add_argument(
        "--output-dir",
        default="reports/profiling",
        help="Folder to write the per-table CSV profiles and the consolidated Excel workbook.",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    csv_files = sorted(glob.glob(os.path.join(args.input_dir, "*.csv")))
    if not csv_files:
        raise SystemExit(f"No CSV files found in {args.input_dir}")

    excel_path = os.path.join(args.output_dir, "data_profiling_report.xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for csv_path in csv_files:
            table_name = os.path.splitext(os.path.basename(csv_path))[0]
            print(f"Profiling table: {table_name}")

            df = pd.read_csv(csv_path, dtype=str)  # read as string first to catch literal "null"
            profile_df = profile_table(df, table_name)

            csv_out = os.path.join(args.output_dir, f"{table_name}_profile.csv")
            profile_df.to_csv(csv_out, index=False)

            # Excel sheet names are capped at 31 chars
            sheet_name = table_name[:31]
            profile_df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"\nProfiling complete. Consolidated workbook saved to: {excel_path}")


if __name__ == "__main__":
    main()
