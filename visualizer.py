"""
Animated visualizer + LLM narrator.
"""

import os, json, logging
from datetime import datetime

import pandas as pd
import plotly.express as px

from common import get_logger

log = get_logger("visualizer", "visualizer.log")
def L(m): print(m); log.info(m)

def _extract_dates(df, preferred=("timestamp", "Timestamp", "created_at", "date")):
    if df.empty: return None
    for col in preferred:
        if col in df.columns:
            try:
                parsed = pd.to_datetime(df[col], errors='coerce')
                if parsed.notna().sum() > 0:
                    return parsed.dt.date
            except Exception: continue
    best = None; best_count = 0
    for col in df.columns:
        try:
            parsed = pd.to_datetime(df[col], errors='coerce')
            count = parsed.notna().sum()
            if count > best_count:
                best = parsed.dt.date; best_count = count
        except Exception: continue
    return best if best_count > 0 else None

def narrate_state(astro, reflexive, mab_weights, recent_trades):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _rule_based_narrative(astro, reflexive, mab_weights, recent_trades)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""You are a quantitative trading analyst. Interpret this system state in 3-4 sentences.
ASTRO: Score {astro.get('astro_score', 0)}, Sun {astro.get('sun_sign','?')}, Moon {astro.get('moon_sign','?')}, Nakshatra {astro.get('nakshatra','?')}
REFLEXIVE: Intensity {reflexive.get('reflexive_intensity', 0)}/10, VIX {reflexive.get('vix_spot', 0)}, Cross-corr {reflexive.get('cross_ticker_correlation', 0)}
MAB WEIGHTS: {json.dumps(mab_weights, indent=2)}
RECENT TRADES: {json.dumps(recent_trades[-5:], indent=2, default=str)}
Reply with a short interpretation."""
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=300,
            messages=[{"role": "user", "content": prompt}])
        return response.content[0].text
    except Exception as e:
        L(f"⚠️ LLM narration failed: {e}")
        return _rule_based_narrative(astro, reflexive, mab_weights, recent_trades)

def _rule_based_narrative(astro, reflexive, mab_weights, recent_trades):
    astro_score = float(astro.get('astro_score', 0) or 0)
    intensity = float(reflexive.get('reflexive_intensity', 0) or 0)
    parts = []
    if astro_score > 3: parts.append("Astrological conditions are bullish.")
    elif astro_score < -3: parts.append("Astrological conditions are bearish.")
    else: parts.append("Astrological conditions are neutral.")
    if intensity > 7: parts.append("Algorithmic herding is elevated — volatility likely.")
    elif intensity > 4: parts.append("Market structure shows moderate coupling.")
    else: parts.append("Market structure is calm.")
    if astro_score > 3 and intensity < 5: parts.append("Overall: conditions favor taking positions.")
    elif astro_score < -3 or intensity > 7: parts.append("Overall: caution advised — reduce exposure.")
    else: parts.append("Overall: mixed signals — stick to the base strategy.")
    return " ".join(parts)

def build_state_space_figure(astro_rows, reflexive_rows, exits_rows):
    if not astro_rows: return None
    astro_df = pd.DataFrame(astro_rows)
    dates = _extract_dates(astro_df)
    if dates is None: return None
    astro_df['date'] = dates
    astro_df = astro_df.dropna(subset=['date'])
    if 'reference' in astro_df.columns:
        nyse_only = astro_df[astro_df['reference'] == 'NYSE']
        if not nyse_only.empty: astro_df = nyse_only
    astro_df = astro_df.sort_values('date').drop_duplicates('date', keep='last')
    if astro_df.empty or 'astro_score' not in astro_df.columns: return None
    merged = astro_df[['date', 'astro_score']].copy()
    if reflexive_rows:
        ref_df = pd.DataFrame(reflexive_rows)
        ref_dates = _extract_dates(ref_df)
        if ref_dates is not None:
            ref_df['date'] = ref_dates
            ref_df = ref_df.dropna(subset=['date'])
            if 'reflexive_intensity' in ref_df.columns:
                ref_df = ref_df.sort_values('date').drop_duplicates('date', keep='last')
                merged = merged.merge(ref_df[['date', 'reflexive_intensity']], on='date', how='left')
    if 'reflexive_intensity' not in merged.columns:
        merged['reflexive_intensity'] = 0
    merged['reflexive_intensity'] = merged['reflexive_intensity'].fillna(0)
    merged['pnl'] = 0.0
    if exits_rows:
        exits_df = pd.DataFrame(exits_rows)
        exit_dates = _extract_dates(exits_df, preferred=("exit_timestamp", "timestamp"))
        if exit_dates is not None:
            exits_df['date'] = exit_dates
            exits_df = exits_df.dropna(subset=['date'])
            if 'pnl_dollars' in exits_df.columns:
                outcome = exits_df.groupby('date')['pnl_dollars'].sum().reset_index()
                outcome.columns = ['date', 'pnl_sum']
                merged = merged.merge(outcome, on='date', how='left')
                if 'pnl_sum' in merged.columns:
                    merged['pnl'] = merged['pnl_sum'].fillna(0)
                    merged = merged.drop(columns=['pnl_sum'])
    merged['pnl'] = merged['pnl'].fillna(0)
    merged['Outcome'] = merged['pnl'].apply(lambda x: 'Win' if x > 0 else ('Loss' if x < 0 else 'No Trade'))
    merged['Size'] = merged['pnl'].abs().apply(lambda x: max(20, min(x / 5, 50)))
    merged['date_str'] = merged['date'].astype(str)
    merged = merged.sort_values('date')
    use_animation = len(merged) >= 5
    common_args = dict(
        x='astro_score', y='reflexive_intensity', color='Outcome', size='Size',
        hover_name='date_str',
        color_discrete_map={'Win': '#22c55e', 'Loss': '#ef4444', 'No Trade': '#94a3b8'})
    if use_animation:
        fig = px.scatter(merged, animation_frame='date_str', animation_group='date_str', **common_args)
    else:
        fig = px.scatter(merged, **common_args)
    fig.update_layout(
        paper_bgcolor='rgba(20,40,80,0.1)', plot_bgcolor='rgba(20,40,80,0.1)',
        font=dict(color='#e8f4ff', family='Trebuchet MS'), height=500, title='', showlegend=True,
        margin=dict(l=40, r=20, t=20, b=40))
    fig.update_xaxes(range=[-10, 10], title='Astro Score')
    fig.update_yaxes(range=[0, 10], title='Reflexive Intensity')
    return fig

def build_signal_heatmap(signals_rows):
    if not signals_rows: return None
    df = pd.DataFrame(signals_rows)
    dates = _extract_dates(df)
    if dates is None: return None
    df['date'] = dates
    df = df.dropna(subset=['date'])
    signal_cols = ['regime', 'rsi', 'sma', 'sentiment', 'congress', 'insider', 'pead', 'flow']
    signal_cols = [c for c in signal_cols if c in df.columns]
    if not signal_cols: return None
    for c in signal_cols:
        df[c] = df[c].apply(lambda x: 1 if x else 0)
    grouped = df.groupby('date')[signal_cols].mean()
    if grouped.empty: return None
    fig = px.imshow(grouped.T, aspect='auto',
                    color_continuous_scale=[[0, '#1e3a5f'], [1, '#a8e4ff']],
                    title='Signal Fire Heatmap (avg per day)')
    fig.update_layout(
        paper_bgcolor='rgba(20,40,80,0.1)', plot_bgcolor='rgba(20,40,80,0.1)',
        font=dict(color='#e8f4ff', family='Trebuchet MS'), height=300)
    return fig
