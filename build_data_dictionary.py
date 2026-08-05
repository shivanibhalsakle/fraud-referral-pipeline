import pandas as pd
import os

rows = [
    ("referral_details_id", "INTEGER", "A unique running number assigned to each row in this report. Used only to identify a specific line item; has no business meaning.", "Always populated. Starts at 101."),
    ("referral_id", "TEXT", "The unique ID of the referral record, i.e. the specific instance of one member referring someone.", "Always populated. Unique per row."),
    ("referral_source", "TEXT", "How the referral was captured: 'User Sign Up' (referee signed up directly online using a referral code), 'Draft Transaction' (referee was linked at the point of an in-club transaction), or 'Lead' (referee started as a sales lead).", "Always populated."),
    ("referral_source_category", "TEXT", "A simplified grouping of referral_source: 'Online' for User Sign Up, 'Offline' for Draft Transaction, or the lead's original marketing source category (e.g. 'Online'/'Offline') when referral_source is 'Lead'.", "Always populated."),
    ("referral_at", "DATE & TIME", "The date and time the referral was created, shown in the local time of the referrer's home club (already converted from the system's UTC storage time).", "Always populated."),
    ("referrer_id", "TEXT", "The unique ID of the existing member who made the referral (the 'referrer').", "May show 'N/A' if the referrer's ID could not be matched to a member record."),
    ("referrer_name", "TEXT", "The referrer's name. NOTE: in this sample/test dataset, names have been anonymized (replaced with random codes) for privacy - in production this would show the real member name.", "'N/A' if unavailable."),
    ("referrer_phone_number", "TEXT", "The referrer's phone number on file.", "'N/A' if unavailable."),
    ("referrer_homeclub", "TEXT", "The gym/club location the referrer is registered to. Club names are kept in their original format (not re-capitalized).", "'N/A' if unavailable."),
    ("referee_id", "TEXT", "The unique ID of the new person being referred (the 'referee'). Only meaningfully populated when referral_source is 'Lead'; for other sources this links back to internal tracking rather than a full member ID.", "'N/A' if unavailable."),
    ("referee_name", "TEXT", "The name of the new person being referred.", "'N/A' if not captured at referral time."),
    ("referee_phone", "TEXT", "The phone number of the new person being referred.", "'N/A' if unavailable."),
    ("referral_status", "TEXT", "The current status of the referral: 'Berhasil' (Successful), 'Menunggu' (Pending/waiting), or 'Tidak Berhasil' (Failed/unsuccessful).", "Always populated."),
    ("num_reward_days", "INTEGER (whole number)", "The size of the reward earned by the referrer, expressed in membership days (e.g. 10, 15, or 20 extra days of membership).", "0 if no reward has been assigned to this referral."),
    ("transaction_id", "TEXT", "The ID of the purchase/transaction associated with this referral (e.g. the referee's membership purchase that triggered the reward).", "'N/A' if no transaction is linked yet."),
    ("transaction_status", "TEXT", "The payment status of the linked transaction, e.g. 'Paid'.", "'N/A' if there is no linked transaction."),
    ("transaction_at", "DATE & TIME", "The date and time the linked transaction occurred, shown in the local time zone of the club/location where the transaction took place.", "Blank if there is no linked transaction."),
    ("transaction_location", "TEXT", "The club/location where the linked transaction took place. Location names are kept in their original format.", "'N/A' if there is no linked transaction."),
    ("transaction_type", "TEXT", "The type of the linked transaction, e.g. 'New' (new membership) or 'Rejoin'.", "'N/A' if there is no linked transaction."),
    ("updated_at", "DATE & TIME", "The date and time this referral record was last updated, shown in the referrer's local time.", "Always populated."),
    ("reward_granted_at", "DATE & TIME", "The date and time the referral reward was actually paid out / granted to the referrer, shown in the referrer's local time.", "Blank if the reward has not been granted yet."),
    ("is_business_logic_valid", "TRUE / FALSE", "The key fraud/quality flag. TRUE means this referral and its reward passed all of our validity checks (or is still legitimately pending with no reward at stake). FALSE means the referral shows a pattern that does not match expected business rules and should be reviewed by the team (e.g. a reward was paid out but the referral was never marked successful, or a transaction exists for a referral that failed).", "Always populated. See 'fraud_check_notes' for the specific reason(s) a row was flagged FALSE."),
    ("fraud_check_notes", "TEXT", "A plain-language note explaining why a referral was flagged FALSE (blank when TRUE). Intended to help the reviewing team quickly understand what looks wrong without re-deriving the logic themselves.", "Blank/'N/A' when is_business_logic_valid is TRUE."),
]

df = pd.DataFrame(rows, columns=["Column Name", "Data Type", "Description (Business Meaning)", "Notes / Constraints"])

notes_df = pd.DataFrame({
    "Topic": [
        "What is this report?",
        "Grain / row count",
        "Time zones",
        "Why some fields show 'N/A'",
        "The is_business_logic_valid flag - how to read it",
        "Anonymized names in this sample",
    ],
    "Explanation": [
        "This report lists every referral submitted through the member referral program and tells you whether the reward tied to it looks legitimate ('valid') or suspicious/inconsistent ('invalid') based on the program's business rules.",
        "One row = one referral. The current dataset contains 46 referrals.",
        "All raw timestamps are stored in UTC. In this report they have been converted to the local time of the relevant club/location so business users see times that match local business hours.",
        "'N/A' means the underlying source data did not have a value for that field for this particular referral (e.g. a referral that never resulted in a purchase will not have transaction details).",
        "TRUE = the referral either (a) was completed successfully with a properly paid, on-time reward, or (b) is still pending/failed with no reward at stake - both are expected, healthy states. FALSE = something about the referral doesn't add up against the program rules (e.g. reward paid without a successful status, transaction happening before the referral even existed, etc.) and should be investigated.",
        "The sample data provided for this exercise has referrer/referee names replaced with anonymized codes to protect privacy. In a live production report, this column would show real member names.",
    ],
})

out_dir = "documentation"
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "data_dictionary.xlsx")

with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
    df.to_excel(writer, sheet_name="Data Dictionary", index=False)
    notes_df.to_excel(writer, sheet_name="How to Read This Report", index=False)

    # Basic column width auto-fit for readability
    for sheet_name, frame in [("Data Dictionary", df), ("How to Read This Report", notes_df)]:
        ws = writer.sheets[sheet_name]
        for i, col in enumerate(frame.columns, 1):
            max_len = max(frame[col].astype(str).map(len).max(), len(col)) + 2
            ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = min(max_len, 70)

print(f"Data dictionary written to {out_path}")
