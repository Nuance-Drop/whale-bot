"""
Adaptive signal allocator using Thompson Sampling.
Beta distributions per signal with exponential decay for non-stationary markets.
"""

import os, json, math, random
from datetime import datetime
import numpy as np

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_MAB_TABLE_ID = os.environ.get("AIRTABLE_MAB_TABLE_ID")

DECAY = 0.95       # Forgetting factor for non-stationary markets
MIN_SAMPLES = 5    # Minimum trades before trusting a signal

# Signal names — must match v10's calc_score
SIGNALS = ["regime", "rsi", "sma", "sentiment", "congress", "insider", "pead", "flow"]

class ThompsonAllocator:
    """
    Thompson Sampling multi-armed bandit for signal weighting.
    Each signal gets Beta(alpha, beta). On each trade decision,
    sample from each posterior and normalize to weights.
    """

    def __init__(self, signals=None):
        self.signals = signals or SIGNALS
        self.alpha = {s: 1.0 for s in self.signals}   # Prior: 1 success
        self.beta = {s: 1.0 for s in self.signals}    # Prior: 1 failure
        self.trade_history = []  # List of (signals_dict, pnl_pct)
        self.load_from_airtable()

    def update(self, signals_fired, pnl_pct):
        """
        Update posteriors after a closed trade.
        signals_fired: dict like {'regime': True, 'rsi': True, ...}
        pnl_pct: realized P/L percentage (e.g., 2.5 or -1.2)
        """
        won = pnl_pct > 0

        # Apply decay to all signals (forgets old observations)
        for s in self.signals:
            self.alpha[s] *= DECAY
            self.beta[s] *= DECAY
            if self.alpha[s] < 0.1: self.alpha[s] = 0.1
            if self.beta[s] < 0.1: self.beta[s] = 0.1

        # Update signals that fired
        for s in self.signals:
            if signals_fired.get(s):
                if won:
                    self.alpha[s] += 1.0
                else:
                    self.beta[s] += 1.0

        self.trade_history.append({
            "signals": signals_fired,
            "pnl": pnl_pct,
            "won": won,
        })

        self.save_to_airtable()

    def get_weights(self):
        """
        Sample from each signal's Beta posterior and normalize.
        Returns dict {signal_name: weight} summing to 1.
        """
        samples = {}
        for s in self.signals:
            samples[s] = np.random.beta(self.alpha[s], self.beta[s])

        total = sum(samples.values())
        if total == 0:
            return {s: 1.0/len(self.signals) for s in self.signals}
        return {s: samples[s] / total for s in self.signals}

    def get_expected_win_rate(self, signal):
        """Mean of Beta posterior = alpha / (alpha + beta)."""
        a, b = self.alpha[signal], self.beta[signal]
        return a / (a + b) if (a + b) > 0 else 0.5

    def get_confidence(self, signal):
        """How many observations support this signal's posterior."""
        return self.alpha[signal] + self.beta[signal] - 2.0  # subtract priors

    def apply_to_score(self, signals_fired):
        """
        Apply learned weights to a signals_fired dict.
        Returns a weighted composite score.
        """
        weights = self.get_weights()
        score = 0.0
        for s in self.signals:
            if signals_fired.get(s):
                score += weights[s]
        # Normalize to a 0-10 scale for compatibility with v10
        return score * 10

    def save_to_airtable(self):
        """Persist current posteriors to Airtable."""
        try:
            if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_MAB_TABLE_ID]):
                return
            from pyairtable import Api
            table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_MAB_TABLE_ID)
            weights = self.get_weights()
            for s in self.signals:
                table.create({
                    "Timestamp": datetime.now().isoformat(),
                    "Bot": "v10",
                    "Signal": s,
                    "Alpha": round(self.alpha[s], 4),
                    "Beta": round(self.beta[s], 4),
                    "Weight": round(weights[s], 4),
                })
        except Exception as e:
            print(f"⚠️ MAB save failed: {e}")

    def load_from_airtable(self):
        """Load most recent posteriors from Airtable."""
        try:
            if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_MAB_TABLE_ID]):
                return
            from pyairtable import Api
            table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_MAB_TABLE_ID)
            # Fetch latest per signal
            rows = table.all(sort=["-Timestamp"])
            seen = set()
            for r in rows:
                sig = r['fields'].get('Signal')
                if sig in seen or sig not in self.signals:
                    continue
                seen.add(sig)
                self.alpha[sig] = float(r['fields'].get('Alpha', 1.0))
                self.beta[sig] = float(r['fields'].get('Beta', 1.0))
            if seen:
                print(f"✅ Loaded MAB state for {len(seen)} signals")
        except Exception as e:
            print(f"⚠️ MAB load failed: {e}")

# Singleton instance
_allocator = None
def get_allocator():
    global _allocator
    if _allocator is None:
        _allocator = ThompsonAllocator()
    return _allocator
