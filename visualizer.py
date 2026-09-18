"""
Animated visualizer + LLM narrator for the Whale Bot Research Lab.
Plots each trading day as a point in (astro_score, reflexive_intensity) space.
Colored by outcome. Animated by date. Narrated by Claude.
"""

import os, json, logging
from datetime import datetime

import pandas as pd
import plotly.express as px

from common import get_logger

log = get_logger("visualizer", "visualizer.log")
def L(m): print(m); log.info(m)

# ============================================================
# LLM NARRATOR
# ============================================================
def narrate_state(astro, reflexive, mab_weights, recent_trades):
    """
    Send current system state to Claude (or OpenAI) for a plain-English
    interpretation. Returns a string. Falls back to a rule-based summary
    if no API key is set.
    """
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
    """Fallback if no LLM API key."""
    astro_score = float(astro.get('Astro_Score', 0))
    intensity = float(reflexive.get('Reflexive_Intensity', 0))

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
# ANIMATED STATE-SPACE SCATTER
# ============================================================
def build_state_space_figure(astro_rows, reflexive_rows, exits_rows):
    """
    Plot each trading day as a point.
    X = astro score, Y = reflexive intensity, color = outcome, size = trade size.
    Animated by date.
    """
    if not astro_rows:
        return None

    astro_df = pd.DataFrame(astro_rows)
    astro_df['date'] = pd.to_datetime(astro_df['Timestamp']).dt.date

    # Deduplicate: one row per day (keep NYSE reference)
    if 'Reference' in astro_df.columns:
        astro_df = astro_df[astro_df['Reference'] == 'NYSE']
    astro_df = astro_df.sort_values('date').drop_duplicates('date', keep='last')

    # Reflexive merge
    if reflexive_rows:
        ref_df = pd.DataFrame(reflexive_rows)
        ref_df['date'] = pd.to_datetime(ref_df['Timestamp']).dt.date
        ref_df = ref_df.sort_values('date').drop_duplicates('date', keep='last')
        merged = astro_df.merge(
            ref_df[['date', 'Reflexive_Intensity', 'VIX_Spot']],
            on='date', how='left'
        )
    else:
        merged = astro_df.copy()
        merged['Reflexive_Intensity'] = 0
        merged['VIX_Spot'] = 0

    # Outcome merge
    if exits_rows:
        exits_df = pd.DataFrame(exits_rows)
        exits_df['date'] = pd.to_datetime(exits_df['Exit Timestamp']).dt.date
        outcome = exits_df.groupby('date')['PnL Dollars'].sum().reset_index()
        outcome.columns = ['date', 'pnl']
        merged = merged.merge(outcome, on='date', how='left')
    else:
        merged['pnl'] = 0

    merged['pnl'] = merged['pnl'].fillna(0)
    merged['Outcome'] = merged['pnl'].apply(
        lambda x: 'Win' if x > 0 else ('Loss' if x < 0 else 'No Trade')
    )
    merged['Size'] = merged['pnl'].abs().apply(lambda x: max(8, min(x / 5, 40)))

    fig = px.scatter(
        merged,
        x='Astro_Score',
        y='Reflexive_Intensity',
        color='Outcome',
        size='Size',
        animation_frame='date',
        animation_group='date',
        hover_name='date',
        hover_data=['VIX_Spot', 'Nakshatra'],
        color_discrete_map={
            'Win': '#22c55e',
            'Loss': '#ef4444',
            'No Trade': '#94a3b8',
        },
        range_x=[-10, 10],
        range_y=[0, 10],
        title='State Space: Astro Score vs Reflexive Intensity'
    )
    fig.update_layout(
        paper_bgcolor='rgba(20,40,80,0.1)',
        plot_bgcolor='rgba(20,40,80,0.1)',
        font=dict(color='#e8f4ff', family='Trebuchet MS'),
        height=500,
    )
    return fig

# ============================================================
# SIGNAL FIRE HEATMAP (alt visualization)
# ============================================================
def build_signal_heatmap(signals_rows):
    """Binary heatmap of which signals fired each day."""
    if not signals_rows:
        return None
    df = pd.DataFrame(signals_rows)
    if 'Timestamp' not in df.columns:
        return None
    df['date'] = pd.to_datetime(df['Timestamp']).dt.date
    signal_cols = ['Regime','RSI','SMA','Sentiment','Congress','Insider','PEAD','Flow']
    signal_cols = [c for c in signal_cols if c in df.columns]
    grouped = df.groupby('date')[signal_cols].mean()

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
