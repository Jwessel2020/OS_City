"""Factory for constructing subsystem threads from configuration."""

from __future__ import annotations

from typing import Any

from src.subsystems.base import SubsystemThread
from src.subsystems.emergency import EmergencyUnit
from src.subsystems.energy import EnergyGrid
from src.subsystems.traffic import TrafficManager
from src.subsystems.waste import WasteOps

SUBSYSTEM_REGISTRY: dict[str, type[SubsystemThread]] = {
    "traffic": TrafficManager,
    "energy": EnergyGrid,
    "waste": WasteOps,
    "emergency": EmergencyUnit,
}


def build_subsystems_from_config(_kernel: object, config: dict[str, Any]) -> list[SubsystemThread]:
    subsystems_config = config.get("subsystems", {})
    instances: list[SubsystemThread] = []

    for subsystem_id, subsystem_params in subsystems_config.items():
        subsystem_type = subsystem_params.get("type", subsystem_id)
        subsystem_cls = SUBSYSTEM_REGISTRY.get(subsystem_type)
        if subsystem_cls is None:
            raise KeyError(f"Unknown subsystem type: {subsystem_type}")

        thread_name = subsystem_params.get("thread_name", subsystem_cls.__name__)
        instance = subsystem_cls(name=thread_name, config=subsystem_params)
        instances.append(instance)

    return instances

