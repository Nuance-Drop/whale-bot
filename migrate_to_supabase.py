import os, json, time
from pyairtable import Api
from supabase import create_client

# --- CONFIG: Load from environment variables ---
AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# --- INIT CLIENTS ---
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
airtable = Api(AIRTABLE_API_KEY)

# --- MIGRATION MAP ---
# Replace the Airtable table IDs with your actual IDs (find them in the Airtable URLs).
# The keys are your Airtable table IDs, and the values are tuples of (Supabase table name, column mapping).
MIGRATIONS = {
    "tblf0GIRypDwoDZSr": ("trades", {
        "Timestamp": "timestamp", "Symbol": "symbol", "Side": "side",
        "Qty": "qty", "Price": "price", "Stop": "stop", "Target": "target",
        "Score": "score", "Threshold": "threshold", "Signal Breakdown": "signal_breakdown"
    }),
    "tblswT1lyfaPeNO7q": ("exits", {
        "Exit Timestamp": "exit_timestamp", "Symbol": "symbol",
        "Entry Price": "entry_price", "Exit Price": "exit_price", "Qty": "qty",
        "Exit Reason": "exit_reason", "PnL Dollars": "pnl_dollars",
        "PnL Percent": "pnl_percent", "Peak Price": "peak_price",
        "Signals That Fired": "signals_that_fired",
        "Signal Score": "signal_score", "Signal Threshold": "signal_threshold",
        "Source": "source", "Fees": "fees"
    }),
    "tblN8WjjufRReEqTh": ("fills", {
        "Timestamp": "timestamp", "Symbol": "symbol", "Order Type": "order_type",
        "Expected Price": "expected_price", "Actual Fill Price": "actual_fill_price",
        "Slippage ($)": "slippage_dollars", "Slippage (%)": "slippage_percent",
        "Order ID": "order_id"
    }),
    "tblB1InLg6HzKdhNC": ("runs", {
        "Timestamp": "timestamp", "Bot": "bot", "Status": "status",
        "Equity": "equity", "Positions Held": "positions_held", "Threshold": "threshold",
        "Top Candidate": "top_candidate", "Top Score": "top_score",
        "Action Taken": "action_taken", "Error": "error"
    }),
    # Add your other table IDs here following the same pattern:
    # "YOUR_SIGNALS_TABLE_ID": ("signals", { ... }),
    # "YOUR_ASTRO_TABLE_ID": ("astro", { ... }),
    # "YOUR_REFLEXIVE_TABLE_ID": ("reflexive", { ... }),
    # "YOUR_MAB_TABLE_ID": ("mab_weights", { ... }),
}

def migrate_table(airtable_table_id, supabase_table_name, mapping):
    print(f"--- Migrating {supabase_table_name} ---")
    try:
        # Fetch all records from the Airtable table
        rows = airtable.table(AIRTABLE_BASE_ID, airtable_table_id).all()
        print(f"  Found {len(rows)} rows in Airtable.")
        
        batch = []
        for row in rows:
            f = row["fields"]
            sb_row = {}
            for at_col, sb_col in mapping.items():
                # Only add the field if it exists in the record
                if at_col in f:
                    sb_row[sb_col] = f[at_col]
            if sb_row: # Ensure we don't insert empty objects
                batch.append(sb_row)

        if batch:
            # Insert in chunks of 500 to be safe
            for i in range(0, len(batch), 500):
                sb.table(supabase_table_name).insert(batch[i:i+500]).execute()
            print(f"  ✅ {len(batch)} rows migrated to {supabase_table_name}.")
        else:
            print(f"  ⚠️ No rows to migrate for {supabase_table_name}.")
    except Exception as e:
        print(f"  ❌ Error migrating {supabase_table_name}: {e}")

if __name__ == "__main__":
    print("Starting migration from Airtable to Supabase...")
    for at_id, (sb_name, mp) in MIGRATIONS.items():
        migrate_table(at_id, sb_name, mp)
    print("\nMigration complete.")
