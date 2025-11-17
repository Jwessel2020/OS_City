"""Dash application providing live controls and dashboard for the simulation."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Iterable

import dash
from dash import Dash, Input, Output, dcc, html
import plotly.graph_objs as go

from src.core.controller import SimulationController

logger = logging.getLogger(__name__)

ASSETS_PATH = Path(__file__).resolve().parent / "assets"
GEO_PATH = ASSETS_PATH / "geo" / "city_zones.geojson"
CITY_GEOJSON = json.loads(GEO_PATH.read_text(encoding="utf-8")) if GEO_PATH.exists() else None
if CITY_GEOJSON:
    for feature in CITY_GEOJSON.get("features", []):
        feature_id = feature.get("properties", {}).get("id")
        if feature_id is not None:
            feature["id"] = feature_id
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

DEFAULT_SLIDER_VALUES = {
    "traffic-slider": 100,
    "signal-slider": 100,
    "energy-slider": 100,
    "renewable-slider": 0,
    "waste-slider": 100,
    "fleet-slider": 6,
    "staff-slider": 8,
}


def build_dashboard_app(controller: SimulationController) -> Dash:
    dash_app = dash.Dash(
        __name__,
        title="Smart City Control Center",
        assets_folder=str(ASSETS_PATH),
        suppress_callback_exceptions=True,
    )

    dash_app.layout = html.Div(
        className="app-shell",
        children=[
            html.Div(
                className="header",
                children=[
                    html.Div(
                        className="header-text",
                        children=[
                            html.H1("Smart City Simulation Control Center"),
                            html.P(
                                "Manage parallel subsystems in real time. Adjust inflow, load, fleets, "
                                "and emergency staffing while watching live performance metrics.",
                                className="subtitle",
                            ),
                        ],
                    ),
                    html.Div(
                        className="status-block",
                        children=[
                            html.Div(id="status-indicator", className="status-indicator"),
                            html.Div(id="tick-display", className="tick-indicator"),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="control-bar",
                children=[
                    html.Button("Start", id="start-btn", n_clicks=0, className="btn btn-primary"),
                    html.Button("Pause / Resume", id="pause-btn", n_clicks=0, className="btn btn-secondary"),
                    html.Button("Reset", id="reset-btn", n_clicks=0, className="btn"),
                    html.Button("Trigger Emergency", id="emergency-btn", n_clicks=0, className="btn btn-danger"),
                ],
            ),
            html.Div(
                className="slider-grid",
                children=[
                    _build_slider(
                        component_id="traffic-slider",
                        label="Traffic Inflow",
                        min_val=40,
                        max_val=200,
                        default=DEFAULT_SLIDER_VALUES["traffic-slider"],
                        formatter=lambda v: f"{v}%",
                    ),
                    _build_slider(
                        "signal-slider",
                        "Signal Responsiveness",
                        min_val=50,
                        max_val=150,
                        default=DEFAULT_SLIDER_VALUES["signal-slider"],
                        formatter=lambda v: f"{v}%",
                        description="Biases junction timing toward longer greens or reds.",
                    ),
                    _build_slider(
                        component_id="energy-slider",
                        label="Energy Base Load",
                        min_val=50,
                        max_val=200,
                        default=DEFAULT_SLIDER_VALUES["energy-slider"],
                        formatter=lambda v: f"{v}%",
                    ),
                    _build_slider(
                        "renewable-slider",
                        "Renewable Boost",
                        min_val=0,
                        max_val=100,
                        default=DEFAULT_SLIDER_VALUES["renewable-slider"],
                        formatter=lambda v: f"{v}%",
                    ),
                    _build_slider(
                        component_id="waste-slider",
                        label="Waste Request Rate",
                        min_val=0,
                        max_val=200,
                        default=DEFAULT_SLIDER_VALUES["waste-slider"],
                        formatter=lambda v: f"{v}%",
                    ),
                    _build_slider(
                        "fleet-slider",
                        "Active Waste Fleet",
                        min_val=2,
                        max_val=16,
                        default=DEFAULT_SLIDER_VALUES["fleet-slider"],
                        formatter=lambda v: f"{int(v)} trucks",
                        step=1,
                    ),
                    _build_slider(
                        "staff-slider",
                        "Emergency Response Units",
                        min_val=4,
                        max_val=24,
                        default=DEFAULT_SLIDER_VALUES["staff-slider"],
                        formatter=lambda v: f"{int(v)} units",
                        step=1,
                    ),
                ],
            ),
            html.Div(
                className="kpi-grid",
                children=[
                    _build_kpi("Grid Efficiency", "kpi-transmission"),
                    _build_kpi("Renewable Mix", "kpi-renewable"),
                    _build_kpi("Storage Round Trip", "kpi-storage"),
                    _build_kpi("Avg Retail Price", "kpi-price"),
                    _build_kpi("Carbon Intensity", "kpi-carbon"),
                ],
            ),
            html.Div(
                className="chart-grid",
                children=[
                    dcc.Graph(
                        id="traffic-chart",
                        className="chart-card chart-wide",
                        style={"height": "320px"},
                        config={"displayModeBar": False, "displaylogo": False},
                    ),
                    dcc.Graph(
                        id="energy-chart",
                        className="chart-card chart-wide",
                        style={"height": "320px"},
                        config={"displayModeBar": False, "displaylogo": False},
                    ),
                    dcc.Graph(
                        id="waste-chart",
                        className="chart-card",
                        style={"height": "320px"},
                        config={"displayModeBar": False, "displaylogo": False},
                    ),
                    dcc.Graph(
                        id="emergency-chart",
                        className="chart-card",
                        style={"height": "320px"},
                        config={"displayModeBar": False, "displaylogo": False},
                    ),
                    dcc.Graph(
                        id="energy-map",
                        className="chart-card chart-wide",
                        style={"height": "360px"},
                        config={"displayModeBar": False, "displaylogo": False},
                    ),
                ],
            ),
            html.Div(
                className="log-card",
                children=[
                    html.Div(
                        className="log-header",
                        children=[
                            html.H3("Latest Metrics Snapshot"),
                            html.Span("Rolling 12-line log of the most recent tick update from each subsystem."),
                        ],
                    ),
                    html.Pre(id="event-log-content", className="log-content"),
                ],
            ),
            dcc.Interval(id="metric-poll", interval=1200, n_intervals=0),
        ],
    )

    register_callbacks(dash_app, controller)
    return dash_app


def _build_slider(
    component_id: str,
    label: str,
    min_val: int,
    max_val: int,
    default: int,
    formatter: Callable[[int], str],
    description: str | None = None,
    step: int = 5,
) -> html.Div:
    children: list[Any] = [
        html.Label(label, htmlFor=component_id),
        dcc.Slider(
            id=component_id,
            min=min_val,
            max=max_val,
            step=step,
            value=default,
            marks={},
            tooltip={"placement": "bottom", "always_visible": False},
            updatemode="drag",
        ),
        html.Div(
            id=f"{component_id}-value",
            className="slider-value",
            children=formatter(default),
        ),
    ]
    if description:
        children.insert(1, html.P(description, className="slider-description"))
    return html.Div(className="slider-control", children=children)


def _build_kpi(label: str, element_id: str) -> html.Div:
    return html.Div(
        className="kpi-card",
        children=[
            html.Span(label, className="kpi-label"),
            html.Span("—", id=element_id, className="kpi-value"),
        ],
    )


def register_callbacks(app: Dash, controller: SimulationController) -> None:
    def register_slider(
        slider_id: str,
        control_key: str,
        transform: Callable[[int], Any],
        formatter: Callable[[int], str],
    ) -> None:
        @app.callback(Output(f"{slider_id}-value", "children"), Input(slider_id, "value"))
        def _update_slider(value: int, _transform=transform, _formatter=formatter, _key=control_key) -> str:
            controller.set_control(_key, _transform(value))
            return _formatter(value)

        _update_slider.__name__ = f"update_{slider_id.replace('-', '_')}"

    register_slider(
        "traffic-slider",
        "traffic_inflow",
        transform=lambda v: v / 100,
        formatter=lambda v: f"{v}%",
    )
    register_slider(
        "signal-slider",
        "traffic_signal_bias",
        transform=lambda v: v / 100,
        formatter=lambda v: f"{v}%",
    )
    register_slider(
        "energy-slider",
        "energy_base_load",
        transform=lambda v: v / 100,
        formatter=lambda v: f"{v}%",
    )
    register_slider(
        "renewable-slider",
        "renewable_boost",
        transform=lambda v: v / 100,
        formatter=lambda v: f"{v}%",
    )
    register_slider(
        "waste-slider",
        "waste_request_rate",
        transform=lambda v: v / 100,
        formatter=lambda v: f"{v}%",
    )
    register_slider(
        "fleet-slider",
        "waste_fleet_size",
        transform=lambda v: int(v),
        formatter=lambda v: f"{int(v)} trucks",
    )
    register_slider(
        "staff-slider",
        "emergency_staff",
        transform=lambda v: int(v),
        formatter=lambda v: f"{int(v)} units",
    )

    @app.callback(
        Output("status-indicator", "children"),
        Output("tick-display", "children"),
        Output("traffic-chart", "figure"),
        Output("energy-chart", "figure"),
        Output("waste-chart", "figure"),
        Output("emergency-chart", "figure"),
        Output("energy-map", "figure"),
        Output("event-log-content", "children"),
        Output("kpi-transmission", "children"),
        Output("kpi-renewable", "children"),
        Output("kpi-storage", "children"),
        Output("kpi-price", "children"),
        Output("kpi-carbon", "children"),
        Input("metric-poll", "n_intervals"),
    )
    def refresh_metrics(_interval: int):
        history = controller.get_history()
        tick = controller.kernel.current_tick()
        status = "Running" if controller.is_running() else "Stopped"

        traffic_fig = _build_line_chart(history.get("traffic", []), "Traffic Network")
        energy_fig = _build_line_chart(history.get("energy", []), "Energy Grid")
        waste_fig = _build_line_chart(history.get("waste", []), "Waste Operations")
        emergency_fig = _build_line_chart(history.get("emergency", []), "Emergency Response")
        latest_energy = history.get("energy", [])
        energy_snapshot = latest_energy[-1][1] if latest_energy else {}
        energy_map = _build_energy_map(energy_snapshot)
        kpis = energy_snapshot.get("kpis", {})

        log_lines: list[str] = []
        for subsystem in ("traffic", "energy", "waste", "emergency"):
            entries = history.get(subsystem, [])
            if not entries:
                continue
            last_tick, metrics = entries[-1]
            preview = ", ".join(
                f"{key}={_format_metric(value)}"
                for key, value in list(metrics.items())[:4]
            )
            log_lines.append(f"[{last_tick}] {subsystem.title()}: {preview}")
        log_text = "\n".join(log_lines[-12:]) or "No metrics yet. Press Start to begin the simulation."

        kpi_transmission = f"{kpis.get('transmission_efficiency', 0) * 100:0.1f}%"
        kpi_renewable = f"{kpis.get('renewable_utilization', 0) * 100:0.1f}%"
        kpi_storage = f"{kpis.get('storage_round_trip_efficiency', 0) * 100:0.1f}%"
        kpi_price = f"${kpis.get('avg_price_mwh', 0):.2f}/MWh"
        kpi_carbon = f"{kpis.get('avg_carbon_intensity', 0):.2f} t/MWh"

        return (
            f"Status: {status}",
            f"Tick: {tick}",
            traffic_fig,
            energy_fig,
            waste_fig,
            emergency_fig,
            energy_map,
            log_text,
            kpi_transmission,
            kpi_renewable,
            kpi_storage,
            kpi_price,
            kpi_carbon,
        )

    @app.callback(Output("start-btn", "n_clicks"), Input("start-btn", "n_clicks"), prevent_initial_call=True)
    def handle_start(_clicks: int):
        controller.start()
        return _clicks

    @app.callback(Output("pause-btn", "n_clicks"), Input("pause-btn", "n_clicks"), prevent_initial_call=True)
    def handle_pause(_clicks: int):
        controller.toggle_pause()
        return _clicks

    @app.callback(
        Output("reset-btn", "n_clicks"),
        Output("traffic-slider", "value"),
        Output("signal-slider", "value"),
        Output("energy-slider", "value"),
        Output("renewable-slider", "value"),
        Output("waste-slider", "value"),
        Output("fleet-slider", "value"),
        Output("staff-slider", "value"),
        Input("reset-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_reset(_clicks: int):
        controller.reset()
        defaults = DEFAULT_SLIDER_VALUES
        return (
            0,
            defaults["traffic-slider"],
            defaults["signal-slider"],
            defaults["energy-slider"],
            defaults["renewable-slider"],
            defaults["waste-slider"],
            defaults["fleet-slider"],
            defaults["staff-slider"],
        )

    @app.callback(Output("emergency-btn", "n_clicks"), Input("emergency-btn", "n_clicks"), prevent_initial_call=True)
    def handle_emergency(_clicks: int):
        controller.trigger_emergency(duration=5.0)
        return 0


def _build_line_chart(history: Iterable[tuple[int, dict[str, Any]]], title: str) -> go.Figure:
    fig = go.Figure()
    metric_series: dict[str, tuple[list[int], list[float]]] = {}
    for tick, metrics in history:
        for key, value in metrics.items():
            numeric = _to_numeric(value)
            if numeric is None:
                continue
            xs, ys = metric_series.setdefault(key, ([], []))
            xs.append(tick)
            ys.append(numeric)

    if metric_series:
        for key, (xs, ys) in metric_series.items():
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines+markers",
                    name=key.replace("_", " ").title(),
                )
            )
    else:
        fig.add_annotation(
            text="Waiting for data…",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color="#94a3b8", size=14),
        )

    fig.update_layout(
        title={"text": title, "y": 0.95, "x": 0.01, "xanchor": "left", "yanchor": "top"},
        margin=dict(l=24, r=24, t=60, b=24),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.85)",
        font=dict(color="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, color="#94a3b8")
    fig.update_yaxes(showgrid=True, gridwidth=0.3, gridcolor="rgba(148,163,184,0.2)", color="#94a3b8")
    return fig


def _build_energy_map(latest_snapshot: dict[str, Any]) -> go.Figure:
    fig = go.Figure()
    zones = latest_snapshot.get("zones", [])
    lines = latest_snapshot.get("lines", [])

    if CITY_GEOJSON and zones:
        zone_values = {zone["id"]: zone.get("price_retail", 0.0) for zone in zones}
        prices = list(zone_values.values())
        zmin = min(prices) if prices else 0.0
        zmax = max(prices) if prices else 1.0
        fig.add_choroplethmapbox(
            geojson=CITY_GEOJSON,
            locations=list(zone_values.keys()),
            z=list(zone_values.values()),
            zmin=zmin,
            zmax=zmax if zmax > zmin else zmin + 1,
            colorscale="Turbo",
            marker_opacity=0.75,
            marker_line_width=1.5,
            colorbar=dict(title="Retail $/MWh"),
            showscale=True,
        )
    elif not zones:
        fig.add_annotation(
            text="Waiting for grid data…",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color="#94a3b8", size=14),
        )

    if zones:
        fig.add_trace(
            go.Scattermapbox(
                lon=[zone.get("lon") for zone in zones],
                lat=[zone.get("lat") for zone in zones],
                mode="markers+text",
                text=[zone.get("name") for zone in zones],
                textposition="top center",
                marker=dict(
                    size=[max(12.0, zone.get("load_mw", 0.0) / 2.5) for zone in zones],
                    color="#0ea5e9",
                    opacity=0.7,
                ),
                hovertemplate=(
                    "%{text}<br>"
                    "Load %{customdata[0]:.1f} MW<br>"
                    "Retail $%{customdata[1]:.2f}/MWh<br>"
                    "Carbon %{customdata[2]:.2f} t/MWh<br>"
                    "Net import %{customdata[3]:.1f} MW"
                ),
                customdata=[
                    [
                        zone.get("load_mw", 0.0),
                        zone.get("price_retail", 0.0),
                        zone.get("carbon_intensity", 0.0),
                        zone.get("net_import_mw", 0.0),
                    ]
                    for zone in zones
                ],
                showlegend=False,
            )
        )

    if lines:
        for line in lines:
            flow = line.get("flow_mw", 0.0)
            util = line.get("utilization", 0.0)
            width = 1.2 + util * 5.0
            color = "#34d399" if flow >= 0 else "#f472b6"
            fig.add_trace(
                go.Scattermapbox(
                    lon=[line.get("from_lon"), line.get("to_lon")],
                    lat=[line.get("from_lat"), line.get("to_lat")],
                    mode="lines",
                    line=dict(width=width, color=color),
                    opacity=0.75,
                    hovertemplate=(
                        f"{line.get('from')} → {line.get('to')}<br>"
                        "Flow %{customdata[0]:.1f} MW<br>"
                        "Utilization %{customdata[1]:.0%}<extra></extra>"
                    ),
                    customdata=[[abs(flow), util]],
                    showlegend=False,
                )
            )

    if zones:
        avg_lat = sum(zone.get("lat", 0.0) for zone in zones) / len(zones)
        avg_lon = sum(zone.get("lon", 0.0) for zone in zones) / len(zones)
    else:
        avg_lat, avg_lon = 40.75, -73.98

    fig.update_layout(
        mapbox=dict(
            style="carto-positron" if MAPBOX_TOKEN else "open-street-map",
            accesstoken=MAPBOX_TOKEN,
            zoom=10.2,
            center={"lat": avg_lat, "lon": avg_lon},
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        title={"text": "Grid Topology (location-aware)", "y": 0.98, "x": 0.02, "xanchor": "left"},
    )
    return fig


def _to_numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)

