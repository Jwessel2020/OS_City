"""Dash application providing live controls and dashboard for the simulation."""

from __future__ import annotations

import logging
from typing import Any

import dash
from dash import Dash, Output, Input, State, dcc, html
import plotly.graph_objs as go

from src.core.controller import ControlState, SimulationController

logger = logging.getLogger(__name__)


def build_dashboard_app(controller: SimulationController) -> Dash:
    dash_app = dash.Dash(__name__, title="Smart City Control Center")

    dash_app.layout = html.Div(
        className="app-container",
        children=[
            html.Div(
                className="header",
                children=[
                    html.H1("Smart City Simulation Control Center"),
                    html.Div(id="status-indicator", className="status-indicator"),
                ],
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button("Start", id="start-btn", n_clicks=0, className="btn btn-start"),
                    html.Button("Pause/Resume", id="pause-btn", n_clicks=0, className="btn btn-pause"),
                    html.Button("Reset", id="reset-btn", n_clicks=0, className="btn"),
                    html.Button("Trigger Emergency", id="emergency-btn", n_clicks=0, className="btn btn-emergency"),
                    html.Div(id="tick-display", className="tick-display"),
                ],
            ),
            html.Div(
                className="sliders",
                children=[
                    _build_slider("traffic-slider", "Traffic Inflow", 0, 300, 100, "%"),
                    _build_slider("energy-slider", "Energy Base Load", 20, 300, 100, "%"),
                    _build_slider("waste-slider", "Waste Request Rate", 0, 300, 100, "%"),
                ],
            ),
            html.Div(
                className="charts",
                children=[
                    dcc.Graph(id="traffic-chart"),
                    dcc.Graph(id="energy-chart"),
                    dcc.Graph(id="waste-chart"),
                    dcc.Graph(id="emergency-chart"),
                ],
            ),
            html.Div(
                className="event-log",
                children=[
                    html.H3("Event Log"),
                    html.Pre(id="event-log-content", className="log-content"),
                ],
            ),
            dcc.Interval(id="metric-poll", interval=1000, n_intervals=0),
        ],
    )

    register_callbacks(dash_app, controller)
    return dash_app


def _build_slider(component_id: str, label: str, min_val: int, max_val: int, default: int, suffix: str) -> html.Div:
    return html.Div(
        className="slider-control",
        children=[
            html.Label(label, htmlFor=component_id),
            dcc.Slider(
                id=component_id,
                min=min_val,
                max=max_val,
                step=1,
                value=default,
                tooltip={"placement": "bottom", "always_visible": True},
            ),
            html.Div(id=f"{component_id}-value", className="slider-value", children=f"{default}{suffix}"),
        ],
    )


def register_callbacks(app: Dash, controller: SimulationController) -> None:
    @app.callback(
        Output("traffic-slider-value", "children"),
        Input("traffic-slider", "value"),
    )
    def update_traffic_value(value: int) -> str:
        controller.set_control("traffic_inflow", value / 100)
        return f"{value}%"

    @app.callback(
        Output("energy-slider-value", "children"),
        Input("energy-slider", "value"),
    )
    def update_energy_value(value: int) -> str:
        controller.set_control("energy_base_load", value / 100)
        return f"{value}%"

    @app.callback(
        Output("waste-slider-value", "children"),
        Input("waste-slider", "value"),
    )
    def update_waste_value(value: int) -> str:
        controller.set_control("waste_request_rate", value / 100)
        return f"{value}%"

    @app.callback(
        Output("status-indicator", "children"),
        Output("tick-display", "children"),
        Output("traffic-chart", "figure"),
        Output("energy-chart", "figure"),
        Output("waste-chart", "figure"),
        Output("emergency-chart", "figure"),
        Output("event-log-content", "children"),
        Input("metric-poll", "n_intervals"),
    )
    def refresh_metrics(_interval: int):
        history = controller.get_history()
        tick = controller.kernel.current_tick()
        status = "Running" if controller.is_running() else "Stopped"

        traffic_fig = _build_line_chart(history.get("traffic", []), "Traffic Metrics")
        energy_fig = _build_line_chart(history.get("energy", []), "Energy Metrics")
        waste_fig = _build_line_chart(history.get("waste", []), "Waste Metrics")
        emergency_fig = _build_line_chart(history.get("emergency", []), "Emergency Metrics")

        log_lines = []
        for subsystem, entries in history.items():
            if not entries:
                continue
            last_tick, last_metrics = entries[-1]
            log_lines.append(f"[{last_tick}] {subsystem.upper()}: {last_metrics}")
        log_text = "\n".join(log_lines[-12:])

        return (
            f"Status: {status}",
            f"Tick: {tick}",
            traffic_fig,
            energy_fig,
            waste_fig,
            emergency_fig,
            log_text,
        )

    @app.callback(
        Output("start-btn", "n_clicks"),
        Input("start-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_start(_clicks: int):
        controller.start()
        return _clicks

    @app.callback(
        Output("pause-btn", "n_clicks"),
        Input("pause-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_pause(_clicks: int):
        controller.toggle_pause()
        return _clicks

    @app.callback(
        Output("reset-btn", "n_clicks"),
        Output("traffic-slider", "value"),
        Output("energy-slider", "value"),
        Output("waste-slider", "value"),
        Input("reset-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_reset(_clicks: int):
        controller.reset()
        return 0, 100, 100, 100

    @app.callback(
        Output("emergency-btn", "n_clicks"),
        Input("emergency-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_emergency(_clicks: int):
        controller.trigger_emergency(duration=5.0)
        return 0


def _build_line_chart(history: list[tuple[int, dict[str, Any]]], title: str) -> go.Figure:
    fig = go.Figure()
    metric_series: dict[str, tuple[list[int], list[float]]] = {}
    for tick, metrics in history:
        for key, value in metrics.items():
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            if not isinstance(value, (int, float)):
                continue
            xs, ys = metric_series.setdefault(key, ([], []))
            xs.append(tick)
            ys.append(float(value))

    for key, (xs, ys) in metric_series.items():
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=key))

    fig.update_layout(title=title, template="plotly_dark")
    return fig

