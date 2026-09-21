"""
Adaptive signal allocator using Thompson Sampling.
Supabase storage backend.
"""

import os, json, math, random
from datetime import datetime
import numpy as np

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

DECAY = 0.95
MIN_SAMPLES = 5

SIGNALS = ["regime", "rsi", "sma", "sentiment", "congress", "insider", "pead", "flow"]

class ThompsonAllocator:
    def __init__(self, signals=None):
        self.signals = signals or SIGNALS
        self.alpha = {s: 1.0 for s in self.signals}
        self.beta = {s: 1.0 for s in self.signals}
        self.trade_history = []
        self.load_from_supabase()

    def update(self, signals_fired, pnl_pct):
        won = pnl_pct > 0
        for s in self.signals:
            self.alpha[s] *= DECAY
            self.beta[s] *= DECAY
            if self.alpha[s] < 0.1: self.alpha[s] = 0.1
            if self.beta[s] < 0.1: self.beta[s] = 0.1
        for s in self.signals:
            if signals_fired.get(s):
                if won: self.alpha[s] += 1.0
                else: self.beta[s] += 1.0
        self.trade_history.append({"signals": signals_fired, "pnl": pnl_pct, "won": won})
        self.save_to_supabase()

    def get_weights(self):
        samples = {s: np.random.beta(self.alpha[s], self.beta[s]) for s in self.signals}
        total = sum(samples.values())
        if total == 0:
            return {s: 1.0/len(self.signals) for s in self.signals}
        return {s: samples[s] / total for s in self.signals}

    def get_expected_win_rate(self, signal):
        a, b = self.alpha[signal], self.beta[signal]
        return a / (a + b) if (a + b) > 0 else 0.5

    def get_confidence(self, signal):
        return self.alpha[signal] + self.beta[signal] - 2.0

    def apply_to_score(self, signals_fired):
        weights = self.get_weights()
        score = 0.0
        for s in self.signals:
            if signals_fired.get(s): score += weights[s]
        return score * 10

    def save_to_supabase(self):
        try:
            if not SUPABASE_URL or not SUPABASE_KEY: return
            from supabase import create_client
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            weights = self.get_weights()
            for s in self.signals:
                sb.table("mab_weights").insert({
                    "timestamp": datetime.now().isoformat(),
                    "bot": "v10", "signal": s,
                    "alpha": round(self.alpha[s], 4),
                    "beta": round(self.beta[s], 4),
                    "weight": round(weights[s], 4),
                }).execute()
        except Exception as e:
            print(f"⚠️ MAB save failed: {e}")

    def load_from_supabase(self):
        try:
            if not SUPABASE_URL or not SUPABASE_KEY: return
            from supabase import create_client
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            r = sb.table("mab_weights").select("*").order("timestamp", desc=True).limit(50).execute()
            seen = set()
            for row in (r.data or []):
                sig = row.get("signal")
                if sig in seen or sig not in self.signals: continue
                seen.add(sig)
                self.alpha[sig] = float(row.get("alpha", 1.0))
                self.beta[sig] = float(row.get("beta", 1.0))
            if seen:
                print(f"✅ Loaded MAB state for {len(seen)} signals")
        except Exception as e:
            print(f"⚠️ MAB load failed: {e}")

_allocator = None
def get_allocator():
    global _allocator
    if _allocator is None:
        _allocator = ThompsonAllocator()
    return _allocator
