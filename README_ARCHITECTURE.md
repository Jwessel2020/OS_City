# Smart City OS - Project Architecture

This document provides a detailed overview of the codebase structure, explaining the responsibility of each file and module in the Smart City simulation platform.

## 📂 GP (Project Root)

The main project directory containing the source code, artifacts, and logs.

### 📄 `main.py`
**Entry Point**: The starting point of the application.
- Parses command-line arguments (`--mode`, `--ticks`, `--config`).
- Bootstraps the `CityKernel`.
- Launches the simulation in the requested mode:
    - `headless`: Runs without UI (good for testing/logging).
    - `dash`: Starts the interactive web dashboard (default).
    - `report`: Runs a quick simulation and generates a static PDF/plot.

---

## 📂 src/core (Core Simulation Logic)

The "brain" of the simulation. These files handle the synchronization, data flow, and intelligence of the city.

### 📄 `src/core/kernel.py`
**The Conductor**: The most critical file.
- **Main Loop**: Runs the central simulation loop (`run()`).
- **Synchronization**: Uses `threading.Barrier` to force all subsystems to step through time together (Tick 1 -> Tick 2).
- **Queue Management**: Holds the `_metrics_queue` buffer where subsystems push their data.
- **Lifecycle**: Manages startup, shutdown, and pausing of all threads.

### 📄 `src/core/controller.py`
**The Bridge**: Connects the Kernel to the outside world (UI).
- **Thread Management**: Spawns the background thread for the kernel.
- **Data Consumption**: Runs a separate `MetricsAggregatorThread` that consumes data from the Kernel's queue so the UI doesn't block the simulation.
- **Control API**: Exposes methods like `set_control()`, `pause()`, and `reset()` for the Dashboard to call.

### 📄 `src/core/context.py`
**Shared Memory**: A thread-safe data store.
- Holds the *latest* known state of every subsystem.
- Used by subsystems to read data from *other* subsystems (e.g., Traffic reading Energy prices).
- Uses `threading.RLock` to prevent race conditions.

### 📄 `src/core/optimizer.py` (Digital Twin Upgrade)
**The AI Tuner**: An automated feedback loop.
- Monitors city metrics (congestion, prices, waste backlog).
- Automatically adjusts control knobs (traffic lights, energy base load) to reach "Local Optimums".
- Implements heuristics to balance conflicting goals (e.g., reducing congestion vs. clearing emergency routes).

### 📄 `src/core/analytics.py` (Digital Twin Upgrade)
**The Analyst**: Real-time insights engine.
- Tracks historical data series.
- Calculates Pearson correlations between variables (e.g., "Does Traffic correlate with Energy Prices?").
- Generates natural language narratives ("⚠️ High Traffic is driving up Emergency Response Time").

---

## 📂 src/subsystems (City Departments)

Each file here represents a distinct "department" of the city, running in its own thread.

### 📄 `src/subsystems/base.py`
**Base Class**: The parent class for all subsystems.
- Handles the threading boilerplate (starting, stopping, waiting for barrier).
- Provides helper methods like `get_metric()` and `publish_metrics()`.

### 📄 `src/subsystems/traffic.py`
**Transportation**: Simulates vehicles, congestion, and road incidents.
- Calculates `congestion_index` and `avg_speed`.
- Estimates CO2 emissions and EV charging demand.
- Affected by: Signal timing, road capacity, energy blackouts.

### 📄 `src/subsystems/energy.py`
**Power Grid**: Simulates electricity generation, consumption, and pricing.
- Manages `zones` (residential, industrial) and `transmission_lines`.
- Calculates `price_retail` and `carbon_intensity`.
- Balances supply (renewable + thermal) vs demand.

### 📄 `src/subsystems/waste.py`
**Sanitation**: Simulates waste collection logistics.
- Manages a fleet of trucks and a queue of pickup requests.
- Calculates `avg_route_km` and `fuel_liters`.
- Efficiency is heavily penalized by Traffic congestion.

### 📄 `src/subsystems/emergency.py`
**911 Services**: Simulates incident response.
- Dispatches units to resolve accidents/fires.
- Calculates `avg_response_min`.
- Response time is degraded by high Traffic congestion.

### 📄 `src/subsystems/factory.py`
**Builder**: A factory pattern helper.
- Reads the configuration file.
- Instantiates the correct subsystem classes based on the config.

---

## 📂 src/viz (Visualization)

The frontend presentation layer.

### 📄 `src/viz/server.py`
**The Dashboard**: A Python Dash/Plotly web application.
- **Layout**: Defines the HTML structure (Charts, Sliders, KPI cards).
- **Callbacks**: Handles UI interactions (Slider moves -> Controller updates).
- **Digital Twin Panel**: Displays the real-time insights from `analytics.py` and `optimizer.py`.

### 📄 `src/viz/dashboard.py` & `report.py`
Legacy/Alternative visualization modes (Matplotlib-based) for headless or static reporting.

---

## 📂 src/data & src/utils

### 📄 `src/data/database.py`
**Persistence**: Handles SQLite storage.
- Saves every simulation tick metrics to `artifacts/smart_city.sqlite3`.
- Allows for replay or post-simulation analysis.

### 📄 `src/data/scenario_default.json`
**Configuration**: The blueprint of the city.
- Defines initial values (population, grid topology, fleet sizes).

### 📄 `src/utils/trace.py`
**Debug Tracing**: High-performance logging.
- Used for low-level debugging of thread synchronization and data flow events.

### 📄 `src/utils/weather.py`
**Environment**: Simulates weather patterns.
- Generates temperature, wind, and solar conditions that affect Energy and Traffic.

