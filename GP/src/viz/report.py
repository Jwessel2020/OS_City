"""Offline reporting helpers for the smart city simulation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Tuple

import matplotlib.pyplot as plt

from src.core.kernel import CityKernel
from src.viz.dashboard import create_plot_config

NumericPoint = Tuple[int, float]
MetricSeries = DefaultDict[str, DefaultDict[str, List[NumericPoint]]]


class TelemetryRecorder:
    """Collect metrics events emitted by the kernel for offline analysis."""

    def __init__(self, kernel: CityKernel) -> None:
        self.kernel = kernel
        self.data: MetricSeries = defaultdict(lambda: defaultdict(list))

    def record(self, timeout: float = 0.5) -> MetricSeries:
        """Block until the simulation finishes and return captured metrics."""

        while True:
            event = self.kernel.metrics_stream(timeout=timeout)
            if event is None:
                if not self.kernel.is_running():
                    break
                continue

            event_type = event.get("type")
            if event_type == "shutdown":
                break

            if event_type != "metrics":
                continue

            subsystem = str(event.get("subsystem", ""))
            metrics = event.get("metrics", {})
            tick = int(event.get("tick", 0))

            for key, value in metrics.items():
                if isinstance(value, bool):
                    numeric = 1.0 if value else 0.0
                elif isinstance(value, (int, float)):
                    numeric = float(value)
                else:
                    continue
                self.data[subsystem][key].append((tick, numeric))

        return self.data


def render_static_dashboard(records: MetricSeries, title: str = "Smart City Report") -> plt.Figure:
    """Render a static dashboard using recorded metrics."""

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(title, fontsize=16)
    config = create_plot_config(axes)

    for subsystem, subsystem_cfg in config.items():
        axis = subsystem_cfg["axis"]
        axis.set_title(subsystem_cfg["title"])
        axis.set_xlabel("Tick")
        axis.set_ylabel(subsystem_cfg["ylabel"])
        axis.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)

        subsystem_data = records.get(subsystem, {})
        for metric_name, props in subsystem_cfg["metrics"].items():
            points = subsystem_data.get(metric_name, [])
            if not points:
                continue

            points.sort(key=lambda p: p[0])
            ticks, values = zip(*points)
            axis.plot(ticks, values, label=props["label"], color=props["color"])

        if subsystem_cfg["metrics"]:
            axis.legend(loc="upper right")

        xmin, xmax = axis.get_xlim()
        if xmin == xmax:
            axis.set_xlim(xmin - 1, xmax + 1)
        ymin, ymax = axis.get_ylim()
        if ymin == ymax:
            pad = 1 if ymin == 0 else abs(ymin) * 0.1
            axis.set_ylim(ymin - pad, ymax + pad)

    plt.tight_layout()
    return fig

