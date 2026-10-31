"""Time-series chart builders for the Charts tab.

Pure functions over the collected ``fred_hist`` / ``market_hist`` frames and saved snapshot
history, returning Plotly figures. Each panel holds one unit on one y-axis; measures with
different scales are separate panels or indexed to a common base, never dual-axis.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Reference categorical palette (fixed order, validated adjacent-pair CVD in both modes).
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]
INK = {
    False: {"text": "#0b0b0b", "secondary": "#52514e", "muted": "#898781", "grid": "#e1e0d9"},
    True: {"text": "#f0efec", "secondary": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a"},
}

WINDOWS = {"3M": pd.DateOffset(months=3), "6M": pd.DateOffset(months=6), "1Y": pd.DateOffset(years=1),
           "2Y": pd.DateOffset(years=2), "All": None}

# Each panel: columns map source label -> (display name, multiplier into the panel unit).
# FRED units: yields/rates in percent; H.4.1 and WRESBAL/WTREGEN in millions; RRPONTSYD in billions.
FRED_PANELS = [
    {"key": "yields", "title": "Treasury yields", "unit": "%", "fmt": ".2f",
     "columns": {"2Y Treasury": ("2Y", 1), "10Y Treasury": ("10Y", 1), "30Y Treasury": ("30Y", 1)}},
    {"key": "real", "title": "Real yields and inflation expectations", "unit": "%", "fmt": ".2f",
     "columns": {"10Y TIPS real yield": ("10Y real", 1), "10Y breakeven inflation": ("10Y breakeven", 1),
                 "5Y5Y forward inflation": ("5Y5Y fwd", 1)}},
    {"key": "curve", "title": "Curve and term premium", "unit": "pp", "fmt": ".2f", "zero_line": True,
     "columns": {"10Y term premium": ("Term premium", 1), "10Y-2Y curve": ("10Y–2Y", 1), "10Y-3M curve": ("10Y–3M", 1)},
     "thresholds": [(0.70, "Term-premium kill 0.70")]},
    {"key": "funding", "title": "Repo funding spreads vs IORB", "unit": "bp", "fmt": ".0f", "zero_line": True,
     "columns": {"SOFR-IORB spread": ("SOFR", 100), "SOFR99-IORB spread": ("SOFR 99th", 100), "TGCR-IORB spread": ("TGCR", 100)},
     "thresholds": [(10, "Median SOFR stress trigger 10bp")]},
    {"key": "liquidity", "title": "Liquidity: reserves, TGA, ON RRP", "unit": "$T", "fmt": ".2f",
     "columns": {"Reserve balances (millions)": ("Reserves", 1e-6), "Treasury General Account (millions)": ("TGA", 1e-6),
                 "ON RRP (billions)": ("ON RRP", 1e-3)}},
    {"key": "fed", "title": "Fed balance sheet", "unit": "$T", "fmt": ".2f",
     "columns": {"Fed balance sheet (millions)": ("Total assets", 1e-6), "Fed Treasury holdings (millions)": ("Treasuries", 1e-6),
                 "Fed MBS holdings (millions)": ("MBS", 1e-6), "Fed Treasury bills (millions)": ("Bills", 1e-6)}},
    {"key": "foreign", "title": "Foreign official custody of Treasuries, YoY change", "unit": "$B", "fmt": ",.0f", "zero_line": True,
     "columns": {"Foreign custody UST YoY change (millions)": ("Custody YoY", 1e-3)},
     "thresholds": [(-300, "Foreign-demand break −$300B")]},
]

MARKET_PANEL = {"key": "markets", "title": "Dollar, gold, oil and long Treasuries (start of window = 100)", "unit": "index",
                "fmt": ".1f", "columns": {"DXY": "DXY", "Gold": "Gold", "Oil": "Oil", "Long Treasuries ETF": "TLT"}}


def window_start(index: pd.Index, label: str) -> pd.Timestamp | None:
    offset = WINDOWS.get(label)
    if offset is None or len(index) == 0:
        return None
    return pd.Timestamp(index.max()) - offset


def _clip(s: pd.Series, start: pd.Timestamp | None) -> pd.Series:
    s = s.dropna()
    if start is not None:
        s = s[s.index >= start]
    return s


def fred_panel_frame(hist: pd.DataFrame, panel: dict, window: str = "1Y") -> pd.DataFrame:
    """Long frame (date, series, value) in the panel's unit. Mixed daily/weekly series keep their own dates."""
    if hist is None or hist.empty:
        return pd.DataFrame(columns=["date", "series", "value"])
    start = window_start(hist.index, window)
    parts = []
    for col, (name, mult) in panel["columns"].items():
        if col not in hist.columns:
            continue
        s = _clip(pd.to_numeric(hist[col], errors="coerce"), start) * mult
        if not s.empty:
            parts.append(pd.DataFrame({"date": s.index, "series": name, "value": s.to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["date", "series", "value"])


def market_panel_frame(market_hist: pd.DataFrame, window: str = "1Y") -> pd.DataFrame:
    if market_hist is None or market_hist.empty:
        return pd.DataFrame(columns=["date", "series", "value"])
    start = window_start(market_hist.index, window)
    parts = []
    for col, name in MARKET_PANEL["columns"].items():
        if col not in market_hist.columns:
            continue
        s = _clip(pd.to_numeric(market_hist[col], errors="coerce"), start)
        if len(s) < 2 or s.iloc[0] == 0:
            continue
        s = 100.0 * s / s.iloc[0]
        parts.append(pd.DataFrame({"date": s.index, "series": name, "value": s.to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["date", "series", "value"])


def risk_history_frame(history: list[dict], regimes: list[str]) -> pd.DataFrame:
    """Long frame of saved regime indices, oldest first, one row per snapshot and regime."""
    rows = []
    for h in history or []:
        ts = pd.to_datetime(h.get("_captured_at") or h.get("timestamp"), errors="coerce", utc=True)
        reg = (h.get("scores") or {}).get("regimes") or {}
        if pd.isna(ts):
            continue
        for name in regimes:
            if reg.get(name) is not None:
                rows.append({"date": ts, "series": name, "value": float(reg[name])})
    df = pd.DataFrame(rows, columns=["date", "series", "value"])
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def _spread_labels(ends: list[tuple[str, float]], span: float) -> dict[str, float]:
    """Nudge end-of-line label y positions apart so close series do not collide."""
    gap = max(span, 1e-9) * 0.07
    placed: dict[str, float] = {}
    last = None
    for name, y in sorted(ends, key=lambda x: x[1]):
        pos = y if last is None else max(y, last + gap)
        placed[name] = pos
        last = pos
    return placed


def _break_gaps(s: pd.DataFrame, max_gap: pd.Timedelta | None) -> pd.DataFrame:
    """Insert a blank point inside any gap longer than ``max_gap`` so the line breaks there."""
    if max_gap is None or len(s) < 2:
        return s
    gaps = s["date"].diff() > max_gap
    if not gaps.any():
        return s
    blanks = pd.DataFrame({"date": s.loc[gaps, "date"] - (s["date"].diff()[gaps] / 2), "value": float("nan")})
    return pd.concat([s[["date", "value"]], blanks]).sort_values("date", kind="stable")


def line_figure(df: pd.DataFrame, *, title: str, unit: str, fmt: str, dark: bool = False,
                zero_line: bool = False, thresholds: list | None = None, y_range: list | None = None,
                order: list[str] | None = None, direct_labels: bool | None = None,
                max_gap: pd.Timedelta | None = None) -> go.Figure:
    palette = SERIES_DARK if dark else SERIES_LIGHT
    ink = INK[dark]
    surface = "#1a1a19" if dark else "#fcfcfb"
    names = order or list(dict.fromkeys(df["series"]))
    names = [n for n in names if n in set(df["series"])]
    fig = go.Figure()
    ends = []
    for i, name in enumerate(names):  # color follows the entity's fixed slot, not its rank
        s = df[df["series"] == name].sort_values("date")
        color = palette[(order.index(name) if order else i) % len(palette)]
        drawn = _break_gaps(s, max_gap)
        fig.add_trace(go.Scatter(
            x=drawn["date"], y=drawn["value"], name=name, mode="lines", line={"width": 2, "color": color},
            connectgaps=False, hovertemplate=f"%{{y:{fmt}}} {unit}<extra>{name}</extra>",
        ))
        fig.add_trace(go.Scatter(  # end marker carries identity next to the direct label
            x=s["date"].iloc[-1:], y=s["value"].iloc[-1:], mode="markers", showlegend=False, hoverinfo="skip",
            cliponaxis=False, marker={"size": 8, "color": color, "line": {"width": 2, "color": surface}},
        ))
        ends.append((name, float(s["value"].iloc[-1]), s["date"].iloc[-1]))
    for value, label in thresholds or []:
        fig.add_hline(y=value, line={"width": 1, "dash": "dash", "color": ink["muted"]},
                      annotation={"text": label, "font": {"size": 11, "color": ink["secondary"]},
                                  "bgcolor": surface, "opacity": 0.9},
                      annotation_position="bottom left")
    if zero_line:
        fig.add_hline(y=0, line={"width": 1, "color": ink["muted"]})
    if direct_labels is None:
        direct_labels = 0 < len(names) <= 4
    right = 12
    if direct_labels and ends:
        values = df["value"].astype(float)
        placed = _spread_labels([(n, y) for n, y, _ in ends], float(values.max() - values.min()))
        for name, y, x in ends:
            fig.add_annotation(x=x, y=placed[name], text=f"{name} {y:{fmt}}", showarrow=False, xanchor="left",
                               xshift=8, font={"size": 11, "color": ink["secondary"]})
        right = 120
    fig.update_layout(
        title={"text": title, "font": {"size": 15, "color": ink["text"]}},
        height=380, margin={"l": 8, "r": right, "t": 40, "b": 64},
        hovermode="x unified", showlegend=len(names) >= 2,
        # Legend below the tick labels so it never collides with the title in half-width columns.
        legend={"orientation": "h", "yanchor": "top", "y": -0.14, "xanchor": "left", "x": 0, "font": {"color": ink["secondary"]}},
    )
    x_range = [df["date"].min(), df["date"].max()] if not df.empty else None
    fig.update_xaxes(showgrid=False, showspikes=True, spikemode="across", spikethickness=1, spikecolor=ink["muted"],
                     tickfont={"color": ink["muted"]}, range=x_range)
    fig.update_yaxes(title={"text": unit, "font": {"color": ink["muted"]}}, gridcolor=ink["grid"], zeroline=False,
                     tickfont={"color": ink["muted"]}, range=y_range)
    return fig


def wide_table(df: pd.DataFrame) -> pd.DataFrame:
    """Table view of a long panel frame: one row per date, one column per series, newest first."""
    if df.empty:
        return df
    out = df.pivot_table(index="date", columns="series", values="value", aggfunc="last").sort_index(ascending=False)
    out.index = pd.Index(pd.to_datetime(out.index).strftime("%Y-%m-%d %H:%M").str.replace(" 00:00", "", regex=False), name="Date")
    out.columns.name = None
    return out.reset_index()
