"""Matplotlib-based dashboard for visualising simulation metrics."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Tuple

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.axes import Axes

from src.core.kernel import CityKernel


Number = float


def create_plot_config(axes: List[List[Axes]]) -> Dict[str, Dict[str, Any]]:
    ax00, ax01 = axes[0]
    ax10, ax11 = axes[1]

    return {
        "traffic": {
            "axis": ax00,
            "metrics": {
                "congestion_index": {"label": "Congestion", "color": "tab:red"},
                "avg_speed_kmh": {"label": "Avg speed (km/h)", "color": "tab:blue"},
            },
            "title": "Traffic Network",
            "ylabel": "Value",
        },
        "energy": {
            "axis": ax01,
            "metrics": {
                "consumption_mw": {"label": "Consumption (MW)", "color": "tab:orange"},
                "generation_mw": {"label": "Generation (MW)", "color": "tab:green"},
                "surplus_mw": {"label": "Surplus (MW)", "color": "tab:cyan"},
            },
            "title": "Energy Grid",
            "ylabel": "Megawatts",
        },
        "waste": {
            "axis": ax10,
            "metrics": {
                "pending_requests": {"label": "Pending requests", "color": "tab:purple"},
                "served_this_tick": {"label": "Served per tick", "color": "tab:brown"},
            },
            "title": "Waste Operations",
            "ylabel": "Requests",
        },
        "emergency": {
            "axis": ax11,
            "metrics": {
                "open_incidents": {"label": "Open incidents", "color": "tab:pink"},
                "severity_index": {"label": "Severity index", "color": "tab:gray"},
            },
            "title": "Emergency Response",
            "ylabel": "Severity / Count",
        },
    }


class SimulationDashboard:
    """Render live plots of subsystem metrics."""

    def __init__(self, kernel: CityKernel, history: int = 240) -> None:
        self.kernel = kernel
        self.history = history
        self._running = True

        self._series: Dict[str, Dict[str, Deque[Tuple[int, Number]]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.history))
        )
        self._fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        self._axes = axes
        self._line_map: Dict[Tuple[str, str], Any] = {}
        self._plot_config = create_plot_config(self._axes)

        self._fig.suptitle("Smart City Simulation Dashboard", fontsize=16)
        self._fig.canvas.mpl_connect("close_event", self._on_close)

        self._init_axes()
        self._animation: FuncAnimation | None = None

    def start(self) -> None:
        """Start the dashboard's animation loop."""

        self._animation = FuncAnimation(
            self._fig,
            self._update,
            interval=500,
            blit=False,
            cache_frame_data=False,
        )
        plt.tight_layout()
        plt.show()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init_axes(self) -> None:
        for subsystem, config in self._plot_config.items():
            axis = config["axis"]
            axis.set_title(config["title"])
            axis.set_xlabel("Tick")
            axis.set_ylabel(config["ylabel"])
            axis.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)

            for metric, props in config["metrics"].items():
                (line,) = axis.plot([], [], label=props["label"], color=props["color"])
                self._line_map[(subsystem, metric)] = line

            axis.legend(loc="upper right")

    def _on_close(self, _event: Any) -> None:
        self._running = False

    def _update(self, _frame: int) -> List[Any]:
        if not self._running:
            plt.close(self._fig)
            return list(self._line_map.values())

        self._drain_metrics_queue()
        self._refresh_plots()
        return list(self._line_map.values())

    def _drain_metrics_queue(self) -> None:
        event = self.kernel.metrics_stream(timeout=0.05)
        while event:
            if event.get("type") == "shutdown":
                self._running = False
                break
            if event.get("type") == "metrics":
                tick = int(event.get("tick", 0))
                subsystem = str(event.get("subsystem", ""))
                metrics = event.get("metrics", {})
                for key, value in metrics.items():
                    if not isinstance(value, (int, float, bool)):
                        continue
                    numeric = float(value)
                    series = self._series[subsystem][key]
                    series.append((tick, numeric))
            event = self.kernel.metrics_stream(timeout=0.0)

    def _refresh_plots(self) -> None:
        for subsystem, config in self._plot_config.items():
            axis = config["axis"]
            updated = False
            for metric in config["metrics"].keys():
                line = self._line_map[(subsystem, metric)]
                points = list(self._series[subsystem][metric])
                if points:
                    ticks, values = zip(*points)
                else:
                    ticks, values = [], []
                line.set_data(ticks, values)
                updated = updated or bool(points)

            if updated:
                axis.relim()
                axis.autoscale_view(True, True, True)
                xmin, xmax = axis.get_xlim()
                if xmin == xmax:
                    axis.set_xlim(xmin - 1, xmax + 1)
                ymin, ymax = axis.get_ylim()
                if ymin == ymax:
                    pad = 1 if ymin == 0 else abs(ymin) * 0.1
                    axis.set_ylim(ymin - pad, ymax + pad)

