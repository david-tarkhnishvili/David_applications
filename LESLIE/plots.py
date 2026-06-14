from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def _label_color(label: str) -> str:
    if label.startswith("Species 1"):
        return "#236393"
    if label.startswith("Species 2"):
        return "#a33b20"
    if label == "Community":
        return "#1b7f3b"
    return "#7c5c1b"


def _label_fill(label: str, alpha: float) -> str:
    if label.startswith("Species 1"):
        return f"rgba(35, 99, 147, {alpha})"
    if label.startswith("Species 2"):
        return f"rgba(163, 59, 32, {alpha})"
    if label == "Community":
        return f"rgba(27, 127, 59, {alpha})"
    return f"rgba(124, 92, 27, {alpha})"


def make_population_figure(frame: pd.DataFrame, label: str, metric: str) -> go.Figure:
    if metric == "total":
        mean_col = "mean_total"
        sd_col = "sd_total"
        title = f"{label}: total population"
    else:
        mean_col = "mean_reproductive"
        sd_col = "sd_reproductive"
        title = f"{label}: reproductive population"

    upper = frame[mean_col] + frame[sd_col]
    lower = (frame[mean_col] - frame[sd_col]).clip(lower=0)
    color = _label_color(label)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=upper,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=lower,
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=_label_fill(label, 0.18),
            name="Mean +/- SD",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame[mean_col],
            mode="lines",
            line=dict(color=color, width=3),
            name="Mean",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title="Individuals",
        template="plotly_white",
        legend_title="Summary",
    )
    return fig


def make_population_comparison_figure(
    frames: dict[str, pd.DataFrame],
    metric: str,
    *,
    include_sd: bool = False,
    title: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    mean_col = "mean_total" if metric == "total" else "mean_reproductive"
    sd_col = "sd_total" if metric == "total" else "sd_reproductive"
    title = title or ("Species comparison: total population" if metric == "total" else "Species comparison: reproductive population")

    for label, frame in frames.items():
        color = _label_color(label)
        if include_sd:
            upper = frame[mean_col] + frame[sd_col]
            lower = (frame[mean_col] - frame[sd_col]).clip(lower=0)
            fig.add_trace(
                go.Scatter(
                    x=frame["year"],
                    y=upper,
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=frame["year"],
                    y=lower,
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor=_label_fill(label, 0.10),
                    name=f"{label} mean +/- SD",
                    hoverinfo="skip",
                )
            )
        fig.add_trace(
            go.Scatter(
                x=frame["year"],
                y=frame[mean_col],
                mode="lines",
                line=dict(color=color, width=3),
                name=label,
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title="Individuals",
        template="plotly_white",
        legend_title="Species",
    )
    return fig


def make_occupancy_figure(frame: pd.DataFrame, label: str) -> go.Figure:
    color = _label_color(label)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["occupancy_proportion"],
            mode="lines",
            line=dict(color=color, width=3),
            name="Occupancy proportion",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["mean_occupied_patches"],
            mode="lines",
            line=dict(color=color, width=2, dash="dash"),
            name="Mean occupied patches",
            yaxis="y2",
        )
    )
    fig.update_layout(
        title=f"{label}: occupancy through time",
        xaxis_title="Year",
        yaxis=dict(title="Occupancy proportion", range=[0, 1]),
        yaxis2=dict(title="Occupied patches", overlaying="y", side="right"),
        template="plotly_white",
        legend_title="Summary",
    )
    return fig


def make_occupancy_comparison_figure(frames: dict[str, pd.DataFrame]) -> go.Figure:
    fig = go.Figure()
    for label, frame in frames.items():
        fig.add_trace(
            go.Scatter(
                x=frame["year"],
                y=frame["occupancy_proportion"],
                mode="lines",
                line=dict(color=_label_color(label), width=3),
                name=label,
            )
        )
    fig.update_layout(
        title="Species comparison: occupancy proportion",
        xaxis_title="Year",
        yaxis_title="Occupancy proportion",
        yaxis=dict(range=[0, 1]),
        template="plotly_white",
        legend_title="Species",
    )
    return fig


def make_persistence_figure(frame: pd.DataFrame, label: str) -> go.Figure:
    color = _label_color(label)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["persistence_probability"],
            mode="lines",
            line=dict(color=color, width=3),
            name="Persistence probability",
        )
    )
    fig.update_layout(
        title=f"{label}: persistence probability",
        xaxis_title="Year",
        yaxis_title="Probability",
        template="plotly_white",
        yaxis=dict(range=[0, 1]),
    )
    return fig


def make_persistence_comparison_figure(frames: dict[str, pd.DataFrame]) -> go.Figure:
    fig = go.Figure()
    for label, frame in frames.items():
        fig.add_trace(
            go.Scatter(
                x=frame["year"],
                y=frame["persistence_probability"],
                mode="lines",
                line=dict(color=_label_color(label), width=3),
                name=label,
            )
        )
    fig.update_layout(
        title="Species comparison: persistence probability",
        xaxis_title="Year",
        yaxis_title="Probability",
        template="plotly_white",
        yaxis=dict(range=[0, 1]),
        legend_title="Species",
    )
    return fig


def make_extinction_histogram(extinction_years: pd.Series, horizon: int, label: str) -> go.Figure:
    observed = extinction_years[extinction_years <= horizon]
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=observed,
            nbinsx=min(max(horizon // 5, 10), 60),
            marker_color=_label_color(label),
            name="Extinction year",
        )
    )
    fig.update_layout(
        title=f"{label}: extinction-time distribution",
        xaxis_title="Extinction year",
        yaxis_title="Replicates",
        template="plotly_white",
    )
    return fig


def make_extinction_comparison_figure(extinction_years_by_label: dict[str, pd.Series], horizon: int) -> go.Figure:
    fig = go.Figure()
    for label, extinction_years in extinction_years_by_label.items():
        observed = extinction_years[extinction_years <= horizon]
        fig.add_trace(
            go.Histogram(
                x=observed,
                nbinsx=min(max(horizon // 5, 10), 60),
                marker_color=_label_color(label),
                opacity=0.55,
                name=label,
            )
        )
    fig.update_layout(
        title="Species comparison: extinction-time distribution",
        xaxis_title="Extinction year",
        yaxis_title="Replicates",
        template="plotly_white",
        barmode="overlay",
        legend_title="Species",
    )
    return fig
