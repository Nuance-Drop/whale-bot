"""
Animated visualizer + LLM narrator for the Whale Bot Research Lab.
Handles missing/misnamed timestamp columns gracefully.
"""

import os, json, logging
from datetime import datetime

import pandas as pd
import plotly.express as px

from common import get_logger

log = get_logger("visualizer", "visualizer.log")
def L(m): print(m); log.info(m)

# ============================================================
# DATE EXTRACTION — resilient to any column name
# ============================================================
def _extract_dates(df, preferred=("Timestamp", "timestamp", "Created", "created",
                                   "Date", "date", "Time", "time")):
    """Return a pandas Series of dates, or None if no date-like column found."""
    if df.empty:
        return None
    # Try preferred names first
    for col in preferred:
        if col in df.columns:
            try:
                parsed = pd.to_datetime(df[col], errors='coerce')
                if parsed.notna().sum() > 0:
                    return parsed.dt.date
            except Exception:
                continue
    # Fallback: try every column, keep the one that parses cleanly
    best = None
    best_count = 0
    for col in df.columns:
        try:
            parsed = pd.to_datetime(df[col], errors='coerce')
            count = parsed.notna().sum()
            if count > best_count:
                best = parsed.dt.date
                best_count = count
        except Exception:
            continue
    if best is not None and best_count > 0:
        return best
    return None

# ============================================================
# LLM NARRATOR
# ============================================================
def narrate_state(astro, reflexive, mab_weights, recent_trades):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _rule_based_narrative(astro, reflexive, mab_weights, recent_trades)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are a quantitative trading analyst. Interpret this system state in 3-4 sentences. Be specific about what the signals suggest.

ASTRO:
- Score: {astro.get('Astro_Score', 0)} (-10 bearish to +10 bullish)
- Sun: {astro.get('Sun_Sign','?')} {astro.get('Sun_Degree',0)}°
- Moon: {astro.get('Moon_Sign','?')} | Phase: {astro.get('Moon_Phase','?')} ({astro.get('Moon_Illumination',0)}% illuminated)
- Mercury Rx: {astro.get('Mercury_Retrograde', False)}
- Nakshatra: {astro.get('Nakshatra','?')}

REFLEXIVE (algorithmic herding):
- Intensity: {reflexive.get('Reflexive_Intensity', 0)}/10
- VIX: {reflexive.get('VIX_Spot', 0)} ({reflexive.get('VIX_Term_Structure','?')})
- Cross-ticker correlation: {reflexive.get('Cross_Ticker_Correlation', 0)}
- Volume Z-score: {reflexive.get('Volume_Z_Score', 0)}

MAB SIGNAL WEIGHTS:
{json.dumps(mab_weights, indent=2)}

RECENT TRADES (last 5):
{json.dumps(recent_trades[-5:], indent=2, default=str)}

Reply with a short interpretation that a non-expert can understand."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        L(f"⚠️ LLM narration failed: {e}")
        return _rule_based_narrative(astro, reflexive, mab_weights, recent_trades)

def _rule_based_narrative(astro, reflexive, mab_weights, recent_trades):
    astro_score = float(astro.get('Astro_Score', 0) or 0)
    intensity = float(reflexive.get('Reflexive_Intensity', 0) or 0)

    parts = []
    if astro_score > 3: parts.append("Astrological conditions are bullish.")
    elif astro_score < -3: parts.append("Astrological conditions are bearish.")
    else: parts.append("Astrological conditions are neutral.")

    if intensity > 7: parts.append("Algorithmic herding is elevated — volatility likely.")
    elif intensity > 4: parts.append("Market structure shows moderate coupling.")
    else: parts.append("Market structure is calm.")

    if astro_score > 3 and intensity < 5:
        parts.append("Overall: conditions favor taking positions.")
    elif astro_score < -3 or intensity > 7:
        parts.append("Overall: caution advised — reduce exposure.")
    else:
        parts.append("Overall: mixed signals — stick to the base strategy.")

    return " ".join(parts)

# ============================================================
# STATE SPACE ANIMATION
# ============================================================
def build_state_space_figure(astro_rows, reflexive_rows, exits_rows):
    """
    Plot each trading day as a point.
    X = astro score, Y = reflexive intensity, color = outcome.
    """
    if not astro_rows:
        L("state space: no astro rows")
        return None

    astro_df = pd.DataFrame(astro_rows)
    if astro_df.empty:
        return None

    # Extract dates
    dates = _extract_dates(astro_df)
    if dates is None:
        L("state space: no valid date column found in astro rows")
        return None
    astro_df['date'] = dates
    astro_df = astro_df.dropna(subset=['date'])

    # Filter to one reference (NYSE) and dedupe by date
    if 'Reference' in astro_df.columns:
        nyse_only = astro_df[astro_df['Reference'] == 'NYSE']
        if not nyse_only.empty:
            astro_df = nyse_only
    astro_df = astro_df.sort_values('date').drop_duplicates('date', keep='last')

    if astro_df.empty:
        return None

    # Ensure Astro_Score column exists
    if 'Astro_Score' not in astro_df.columns:
        L("state space: no Astro_Score column")
        return None

    # Merge reflexive
    merged = astro_df[['date', 'Astro_Score']].copy()
    if reflexive_rows:
        ref_df = pd.DataFrame(reflexive_rows)
        if not ref_df.empty:
            ref_dates = _extract_dates(ref_df)
            if ref_dates is not None:
                ref_df['date'] = ref_dates
                ref_df = ref_df.dropna(subset=['date'])
                if 'Reflexive_Intensity' in ref_df.columns:
                    ref_df = ref_df.sort_values('date').drop_duplicates('date', keep='last')
                    merged = merged.merge(
                        ref_df[['date', 'Reflexive_Intensity']],
                        on='date', how='left'
                    )
    if 'Reflexive_Intensity' not in merged.columns:
        merged['Reflexive_Intensity'] = 0
    merged['Reflexive_Intensity'] = merged['Reflexive_Intensity'].fillna(0)

    # Merge exits outcome
    merged['pnl'] = 0.0
    if exits_rows:
        exits_df = pd.DataFrame(exits_rows)
        if not exits_df.empty:
            exit_dates = _extract_dates(exits_df, preferred=("Exit Timestamp", "Timestamp"))
            if exit_dates is not None:
                exits_df['date'] = exit_dates
                exits_df = exits_df.dropna(subset=['date'])
                if 'PnL Dollars' in exits_df.columns:
                    outcome = exits_df.groupby('date')['PnL Dollars'].sum().reset_index()
                    outcome.columns = ['date', 'pnl']
                    merged = merged.merge(outcome, on='date', how='left')
                    merged['pnl'] = merged['pnl_y'].fillna(0) if 'pnl_y' in merged.columns else merged['pnl'].fillna(0)
                    if 'pnl_x' in merged.columns:
                        merged = merged.drop(columns=['pnl_x'])
                    if 'pnl_y' in merged.columns:
                        merged = merged.rename(columns={'pnl_y': 'pnl'})

    merged['pnl'] = merged['pnl'].fillna(0)
    merged['Outcome'] = merged['pnl'].apply(
        lambda x: 'Win' if x > 0 else ('Loss' if x < 0 else 'No Trade')
    )
    merged['Size'] = merged['pnl'].abs().apply(lambda x: max(8, min(x / 5, 40)))

    # Convert date to string for plotly animation
    merged['date_str'] = merged['date'].astype(str)

    # Sort by date
    merged = merged.sort_values('date')

    # If only a few rows, show static scatter (animation not useful)
    use_animation = len(merged) >= 5

    if use_animation:
        fig = px.scatter(
            merged,
            x='Astro_Score',
            y='Reflexive_Intensity',
            color='Outcome',
            size='Size',
            animation_frame='date_str',
            animation_group='date_str',
            hover_name='date_str',
            color_discrete_map={'Win': '#22c55e', 'Loss': '#ef4444', 'No Trade': '#94a3b8'},
            range_x=[-10, 10],
            range_y=[0, 10],
            title='State Space: Astro Score vs Reflexive Intensity'
        )
    else:
        fig = px.scatter(
            merged,
            x='Astro_Score',
            y='Reflexive_Intensity',
            color='Outcome',
            size='Size',
            hover_name='date_str',
            color_discrete_map={'Win': '#22c55e', 'Loss': '#ef4444', 'No Trade': '#94a3b8'},
            range_x=[-10, 10],
            range_y=[0, 10],
            title='State Space: Astro Score vs Reflexive Intensity (accumulating)'
        )

    fig.update_layout(
        paper_bgcolor='rgba(20,40,80,0.1)',
        plot_bgcolor='rgba(20,40,80,0.1)',
        font=dict(color='#e8f4ff', family='Trebuchet MS'),
        height=500,
    )
    return fig

# ============================================================
# SIGNAL FIRE HEATMAP
# ============================================================
def build_signal_heatmap(signals_rows):
    if not signals_rows:
        return None
    df = pd.DataFrame(signals_rows)
    if df.empty:
        return None

    dates = _extract_dates(df)
    if dates is None:
        return None
    df['date'] = dates
    df = df.dropna(subset=['date'])

    signal_cols = ['Regime', 'RSI', 'SMA', 'Sentiment', 'Congress', 'Insider', 'PEAD', 'Flow']
    signal_cols = [c for c in signal_cols if c in df.columns]
    if not signal_cols:
        return None

    # Coerce checkbox values to 0/1
    for c in signal_cols:
        df[c] = df[c].apply(lambda x: 1 if x else 0)

    grouped = df.groupby('date')[signal_cols].mean()
    if grouped.empty:
        return None

    fig = px.imshow(
        grouped.T,
        aspect='auto',
        color_continuous_scale=[[0, '#1e3a5f'], [1, '#a8e4ff']],
        title='Signal Fire Heatmap (avg per day)'
    )
    fig.update_layout(
        paper_bgcolor='rgba(20,40,80,0.1)',
        plot_bgcolor='rgba(20,40,80,0.1)',
        font=dict(color='#e8f4ff', family='Trebuchet MS'),
        height=300,
    )
    return fig
