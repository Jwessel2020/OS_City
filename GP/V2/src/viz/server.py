import dash
from dash import dcc, html, Input, Output
import plotly.graph_objs as go
import sqlite3
import pandas as pd
from src.core.kernel import CitySimulation
import threading
import time

# Global Simulation Instance (Singleton for the Dashboard)
SIM = CitySimulation()

app = dash.Dash(__name__, title="OS City V2 Control")

app.layout = html.Div([
    html.H1("OS City V2: Process & Concurrency Monitor"),
    
    html.Div([
        html.Button("Start Simulation", id="btn-start", n_clicks=0),
        html.Button("Stop Simulation", id="btn-stop", n_clicks=0),
        html.Div(id="status-display", style={"display": "inline-block", "marginLeft": "20px"})
    ], style={"marginBottom": "20px"}),
    
    html.Div([
        html.H3("Performance & Latency (SQL Derived)"),
        dcc.Graph(id="perf-graph"),
    ]),
    
    html.Div([
        html.H3("Queue Health"),
        dcc.Graph(id="queue-graph"),
    ]),
    
    dcc.Interval(id="poll-interval", interval=1000, n_intervals=0)
])

@app.callback(
    [Output("status-display", "children"),
     Output("perf-graph", "figure"),
     Output("queue-graph", "figure")],
    [Input("poll-interval", "n_intervals"),
     Input("btn-start", "n_clicks"),
     Input("btn-stop", "n_clicks")]
)
def update_dashboard(n, start_clicks, stop_clicks):
    ctx = dash.callback_context
    if ctx.triggered:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if button_id == "btn-start":
            SIM.bootstrap()
            SIM.start()
        elif button_id == "btn-stop":
            SIM.stop()
            
    status = "Running" if SIM.running.is_set() else "Stopped"
    
    # Fetch Data from SQLite for Graphs
    # We read directly from the DB file to demonstrate SQL logging integration
    conn = sqlite3.connect(str(SIM.logger.db_path), check_same_thread=False)
    
    # 1. Performance Query: Avg Latency per Subsystem (Windowed)
    try:
        perf_df = pd.read_sql_query("""
            SELECT subsystem, seq, latency_ms 
            FROM ticks 
            WHERE run_id = ? 
            ORDER BY seq DESC LIMIT 100
        """, conn, params=(SIM.logger.run_id,))
    except:
        perf_df = pd.DataFrame(columns=["subsystem", "seq", "latency_ms"])

    # 2. Queue Stats Query
    try:
        queue_df = pd.read_sql_query("""
            SELECT queue_name, size, capacity, dropped, ts_mono
            FROM queue_stats
            WHERE run_id = ?
            ORDER BY ts_mono DESC LIMIT 50
        """, conn, params=(SIM.logger.run_id,))
    except:
        queue_df = pd.DataFrame(columns=["queue_name", "size", "capacity", "dropped"])
        
    conn.close()
    
    # Build Perf Graph
    perf_fig = go.Figure()
    for sub in perf_df['subsystem'].unique():
        df_sub = perf_df[perf_df['subsystem'] == sub]
        perf_fig.add_trace(go.Scatter(
            x=df_sub['seq'], y=df_sub['latency_ms'], 
            mode='lines+markers', name=f"{sub} Latency"
        ))
    perf_fig.update_layout(title="Tick Latency (ms)", xaxis_title="Tick Sequence", yaxis_title="ms")
    
    # Build Queue Graph
    queue_fig = go.Figure()
    if not queue_df.empty:
        queue_fig.add_trace(go.Scatter(
            x=queue_df.index, y=queue_df['size'], 
            mode='lines', name="Queue Size", fill='tozeroy'
        ))
        queue_fig.add_trace(go.Scatter(
            x=queue_df.index, y=queue_df['capacity'], 
            mode='lines', name="Capacity", line=dict(dash='dash')
        ))
    queue_fig.update_layout(title="Buffer Occupancy", xaxis_title="Time (samples)", yaxis_title="Items")

    return f"Status: {status} | Run ID: {SIM.logger.run_id}", perf_fig, queue_fig

def run_server():
    app.run(debug=True, use_reloader=False)

if __name__ == "__main__":
    run_server()

