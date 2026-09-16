"""
Unit tests for core scoring logic. No API keys required.
Run: python -m pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import math
import pandas as pd
import pytest

from common import (
    score_mult, calc_dynamic_threshold_base, atr_multiplier_from_series,
    clean_for_json
)

def test_score_mult_returns_expected_values():
    assert score_mult(4.0, 4.0) == 0.5
    assert score_mult(3.0, 4.0) == 0.5
    assert score_mult(5.0, 4.0) == 0.75
    assert score_mult(6.0, 4.0) == 1.0
    assert score_mult(7.0, 4.0) == 1.25
    assert score_mult(9.0, 4.0) == 1.5

def test_regime_block_when_below_200ma():
    t, reasons = calc_dynamic_threshold_base(regime_strength=-1.0, vix=20, num_positions=0)
    assert t == 999
    assert "regime_block" in reasons

def test_threshold_increases_with_vix_and_holdings():
    base, _ = calc_dynamic_threshold_base(3.0, 18, 0)
    assert base == 4.0
    high_vix, _ = calc_dynamic_threshold_base(3.0, 35, 0)
    assert high_vix == 6.0
    holding, _ = calc_dynamic_threshold_base(3.0, 18, 2)
    assert holding == 5.0
    strong, _ = calc_dynamic_threshold_base(8.0, 12, 0)
    assert strong == 3.0

def test_atr_multiplier_capped():
    n = 100
    high = pd.Series([101.0] * n)
    low = pd.Series([99.0] * n)
    close = pd.Series([100.0] * n)
    assert atr_multiplier_from_series(high, low, close) == 1.0

    high_hi = pd.Series([100.1] * 80 + [110.0] * 20)
    low_hi = pd.Series([99.9] * 80 + [90.0] * 20)
    close_hi = pd.Series([100.0] * 100)
    m2 = atr_multiplier_from_series(high_hi, low_hi, close_hi)
    assert 0.5 <= m2 <= 1.5

def test_clean_for_json_handles_nan_and_inf():
    bad = {"a": float("nan"), "b": float("inf"), "c": -float("inf"),
           "d": [1.0, float("nan")], "e": {"f": float("nan")}}
    cleaned = clean_for_json(bad)
    assert cleaned["a"] == 0
    assert cleaned["b"] == 0
    assert cleaned["c"] == 0
    assert cleaned["d"][1] == 0
    assert cleaned["e"]["f"] == 0
    assert clean_for_json({"x": 1.5})["x"] == 1.5
