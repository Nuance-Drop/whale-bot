# ============================================================
# DYNAMIC THRESHOLD ENGINE
# ============================================================
def get_vix_level():
    """Get current VIX level."""
    try:
        vix = yf.download("^VIX", period="5d", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        return float(vix['Close'].iloc[-1])
    except Exception:
        return 20.0  # assume normal if we can't get it

def get_spy_regime_strength():
    """Returns how far SPY is above/below its 200MA (as %)."""
    try:
        spy = yf.download("SPY", period="1y", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        spy['SMA200'] = spy['Close'].rolling(200).mean()
        last = spy.iloc[-1]
        return (last['Close'] - last['SMA200']) / last['SMA200'] * 100
    except Exception:
        return 0.0

def is_earnings_season():
    """True if current month is a peak earnings month."""
    return datetime.now().month in [1, 4, 7, 10]

def is_macro_event_week():
    """Check for Fed meetings, CPI, NFP in next 3 days."""
    # Simplified — in production, use an economic calendar API
    # This is a stub that checks for first Friday of month (NFP)
    now = datetime.now()
    if now.weekday() == 4 and now.day <= 7:  # First Friday
        return True
    return False

def get_win_streak():
    """Read trade log to calculate consecutive wins/losses."""
    try:
        if not os.path.isfile(LOG_FILE):
            return 0
        df = pd.read_csv(LOG_FILE)
        if len(df) < 2:
            return 0
        # Simplified: return 0 for now
        return 0
    except Exception:
        return 0

def get_peak_equity():
    """Read bot.log or track peak equity separately."""
    # For now, assume peak = current (no drawdown tracking yet)
    return None

def calculate_dynamic_threshold(equity, num_positions, log):
    """
    Returns the dynamic threshold based on current market conditions.
    Base threshold is 4. Adjusted by circumstances.
    """
    threshold = 4
    reasons = []

    # Market regime strength
    regime_strength = get_spy_regime_strength()
    if regime_strength < 0:
        log(f"  🚫 SPY below 200MA ({regime_strength:.1f}%) — BLOCK ALL TRADES")
        return 999, ["regime_block"]
    elif regime_strength < 2:
        threshold += 1
        reasons.append(f"Fragile regime (+1, SPY only +{regime_strength:.1f}% above 200MA)")
    elif regime_strength > 5:
        threshold -= 1
        reasons.append(f"Strong bull (-1, SPY +{regime_strength:.1f}%)")

    # VIX level
    vix = get_vix_level()
    if vix > 30:
        threshold += 2
        reasons.append(f"VIX {vix:.1f} > 30 (+2, high fear)")
    elif vix > 20:
        threshold += 1
        reasons.append(f"VIX {vix:.1f} elevated (+1)")
    elif vix < 15:
        threshold -= 1
        reasons.append(f"VIX {vix:.1f} < 15 (-1, complacent)")

    # Earnings season
    if is_earnings_season():
        threshold += 1
        reasons.append("Earnings season (+1)")

    # Macro events
    if is_macro_event_week():
        threshold += 1
        reasons.append("Macro event week (+1)")

    # Position count
    if num_positions >= 2:
        threshold += 1
        reasons.append(f"Already holding {num_positions} positions (+1)")

    # Time of day
    now = datetime.now(timezone.utc)
    hour = now.hour
    if now.weekday() == 0 and hour < 16:  # Monday morning ET
        threshold += 1
        reasons.append("Monday morning (+1)")
    if now.weekday() == 4 and hour >= 19:  # Friday afternoon ET
        threshold += 1
        reasons.append("Friday afternoon (+1)")

    # Cap threshold between 3 and 8
    threshold = max(3, min(threshold, 8))
    return threshold, reasons

# ============================================================
# POSITION SIZING SCALER
# ============================================================
def calculate_position_multiplier(score, threshold):
    """Scale position size based on conviction above threshold."""
    if score <= threshold:
        return 0.5      # Barely qualified
    elif score == threshold + 1:
        return 0.75
    elif score == threshold + 2:
        return 1.0      # Standard
    elif score == threshold + 3:
        return 1.25
    else:
        return 1.5      # Maximum conviction

# ============================================================
# MAIN BOT (Updated)
# ============================================================
def run_bot():
    log("=" * 60)
    log(f"Bot v5 started at {datetime.now().isoformat()}")

    now = datetime.now(timezone.utc)
    if now.weekday() >= 5 or now.hour < 14 or now.hour >= 21:
        log("Market closed. Exiting.")
        return

    try:
        account = client.get_account()
        equity = float(account.equity)
        open_positions = client.get_all_positions()
        position_symbols = [p.symbol for p in open_positions]

        orders_request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        open_orders = client.get_orders(filter=orders_request)
        order_symbols = [o.symbol for o in open_orders]
        already_held = set(position_symbols + order_symbols)

        total_position_value = sum([float(p.market_value) for p in open_positions])
        tactical_limit = equity * TACTICAL_LIMIT_PCT

        log(f"Equity: ${equity:.2f} | Exposure: ${total_position_value:.2f} | Limit: ${tactical_limit:.2f}")

        # === DYNAMIC THRESHOLD ===
        threshold, reasons = calculate_dynamic_threshold(equity, len(already_held), log)
        log(f"📊 DYNAMIC THRESHOLD: {threshold} (base was 4)")
        for reason in reasons:
            log(f"   → {reason}")

        if threshold > 8:
            log("🚫 Threshold exceeds max score. No trades today.")
            return

        if total_position_value >= tactical_limit:
            log("⚠️ Tactical limit reached.")
            return
        if len(already_held) >= MAX_POSITIONS:
            log(f"⚠️ Max positions ({MAX_POSITIONS}) reached.")
            return

        # Score all candidates
        candidates = []
        for symbol in WATCHLIST:
            if symbol in already_held:
                log(f"⏸️ {symbol}: Already held.")
                continue
            score, signals = calculate_score(symbol)
            if score >= threshold:
                candidates.append((symbol, score))
            else:
                log(f"  ❌ {symbol}: Score {score} below threshold {threshold}")

        if not candidates:
            log("No tickers met the dynamic threshold.")
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        symbol, score = candidates[0]
        multiplier = calculate_position_multiplier(score, threshold)
        log(f"🎯 TRADING {symbol} (Score: {score}/{threshold}) | Size multiplier: {multiplier}x")

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", auto_adjust=True)
        price = float(hist['Close'].iloc[-1])

        remaining_tactical = tactical_limit - total_position_value
        risk_amount = equity * RISK_PER_TRADE * multiplier
        risk_per_share = price * STOP_LOSS_PCT
        qty = min(int(risk_amount / risk_per_share), int(remaining_tactical / price))

        if qty < 1:
            log(f"⚠️ Not enough room for 1 share of {symbol}.")
            return

        place_bracket_order(symbol, OrderSide.BUY, qty, price)

    except Exception as e:
        log(f"❌ Bot error: {e}")

    log("Bot cycle complete.")
    log("=" * 60)
