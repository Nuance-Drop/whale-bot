"""Runs every Sunday. Reads Airtable, computes IC per signal, writes new weights."""
import os, json, requests, numpy as np
from datetime import datetime
from collections import defaultdict

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE_ID = os.environ["AIRTABLE_TABLE_ID"]
AIRTABLE_EXITS_TABLE_ID = os.environ["AIRTABLE_EXITS_TABLE_ID"]

BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

def fetch(table_id):
    records, params = [], {}
    while True:
        r = requests.get(f"{BASE_URL}/{table_id}", headers=HEADERS, params=params, timeout=30)
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset: break
        params["offset"] = offset
    return records

def main():
    print("Fetching Airtable data...")
    trades = fetch(AIRTABLE_TABLE_ID)
    exits = fetch(AIRTABLE_EXITS_TABLE_ID)
    print(f"  {len(trades)} trades, {len(exits)} exits")

    exits_by_sym = defaultdict(list)
    for e in exits:
        exits_by_sym[e["fields"].get("Symbol")].append(e["fields"])

    matched = []
    for t in trades:
        tf = t["fields"]
        sym = tf.get("Symbol")
        if sym not in exits_by_sym: continue
        import pandas as pd
        entry_ts = pd.Timestamp(tf.get("Timestamp"))
        candidates = [e for e in exits_by_sym[sym]
                      if pd.Timestamp(e.get("Exit Timestamp")) > entry_ts]
        if not candidates: continue
        ex = min(candidates, key=lambda e: pd.Timestamp(e["Exit Timestamp"]))
        try:
            signals = json.loads(tf.get("Signal Breakdown", "{}").replace("'", '"'))
        except Exception:
            signals = {}
        matched.append({
            "symbol": sym,
            "pnl_pct": ex.get("PnL Percent", 0),
            "signals": signals
        })

    print(f"Matched {len(matched)} pairs")
    if len(matched) < 10:
        print("⚠️ Fewer than 10 trades — keeping current weights")
        return

    # Compute IC per signal
    ALL = ["regime", "rsi", "sma", "sentiment", "congress", "insider", "pead", "flow"]
    ic = {}
    for sig in ALL:
        fires = np.array([1 if m["signals"].get(sig) else 0 for m in matched])
        rets = np.array([m["pnl_pct"] for m in matched])
        if fires.sum() < 3 or fires.std() == 0 or rets.std() == 0:
            ic[sig] = 0.0
            continue
        ic[sig] = float(np.corrcoef(fires, rets)[0, 1])

    print("\nIC per signal:")
    for k, v in sorted(ic.items(), key=lambda x: -abs(x[1])):
        print(f"  {k}: {v:+.4f}")

    # Softmax with min floor
    shifted = {k: max(v + 0.5, 0.01) for k, v in ic.items()}
    vals = np.array(list(shifted.values()))
    exp = np.exp(vals / 1.5)
    weights = exp / exp.sum()
    weights = np.maximum(weights, 0.05)
    weights = weights / weights.sum()

    # Scale to match old point system (so threshold logic still works)
    old_scale = {"regime": 1, "rsi": 1, "sma": 1, "sentiment": 1,
                 "congress": 2, "insider": 2, "pead": 1, "flow": 2}
    total_old = sum(old_scale.values())
    new_weights = {k: round(float(w) * total_old, 4) for k, w in zip(shifted.keys(), weights)}

    print("\nNew weights:")
    for k, v in new_weights.items():
        print(f"  {k}: {v}")

    with open("signal_weights.json", "w") as f:
        json.dump(new_weights, f, indent=2)
    print("\n✅ Written to signal_weights.json")

if __name__ == "__main__":
    main()
