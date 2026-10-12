"""Runs every Sunday. Reads Supabase, computes IC per signal, writes new weights."""
import os, json, requests, numpy as np
import pandas as pd
from collections import defaultdict

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

def fetch(table):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        raise Exception(f"Supabase error {r.status_code}: {r.text}")
    return r.json()

def main():
    print("Fetching Supabase data...")
    trades = fetch("trades")
    exits = fetch("exits")
    print(f"  {len(trades)} trades, {len(exits)} exits")

    exits_by_sym = defaultdict(list)
    for e in exits:
        exits_by_sym[e.get("symbol")].append(e)

    matched = []
    for t in trades:
        sym = t.get("symbol")
        if sym not in exits_by_sym: 
            continue
        
        entry_ts = pd.Timestamp(t.get("timestamp"))
        candidates = [e for e in exits_by_sym[sym]
                      if pd.Timestamp(e.get("exit_timestamp")) > entry_ts]
        
        if not candidates: 
            continue
        
        ex = min(candidates, key=lambda e: pd.Timestamp(e["exit_timestamp"]))
        
        try:
            raw_breakdown = t.get("signal_breakdown", "{}")
            if raw_breakdown:
                signals = json.loads(raw_breakdown.replace("'", '"'))
            else:
                signals = {}
        except Exception as e:
            print(f"Failed to parse signal_breakdown for trade {t.get('id')}: {e}")
            signals = {}
            
        matched.append({
            "symbol": sym,
            "pnl_pct": float(ex.get("pnl_percent", 0) or 0),
            "signals": signals
        })

    print(f"Matched {len(matched)} pairs")
    if len(matched) < 10:
        print("⚠️ Fewer than 10 trades — keeping current weights")
        return

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

    shifted = {k: max(v + 0.5, 0.01) for k, v in ic.items()}
    vals = np.array(list(shifted.values()))
    exp = np.exp(vals / 1.5)
    weights = exp / exp.sum()
    weights = np.maximum(weights, 0.05)
    weights = weights / weights.sum()

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
