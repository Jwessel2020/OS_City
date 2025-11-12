"""Emergency response subsystem monitoring and dispatching incidents."""

from __future__ import annotations

import logging
import random
from typing import Any

from src.subsystems.base import SubsystemThread

logger = logging.getLogger(__name__)


class EmergencyUnit(SubsystemThread):
    """Model emergency incident processing."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._priority_threshold = cfg.get("priority_threshold", 0.6)
        self._rng = random.Random(cfg.get("seed"))
        self._open_incidents = 0
        self._resolved_incidents = 0

    def execute_tick(self) -> None:
        incident_chance = self._rng.random()
        if incident_chance > 0.7:
            new_incidents = self._rng.randint(1, 3)
            self._open_incidents += new_incidents
            logger.debug("Emergency tick: registered %d new incidents", new_incidents)

        if self._open_incidents:
            resolution_rate = self._priority_threshold + self._rng.uniform(-0.2, 0.2)
            resolved = min(self._open_incidents, max(int(resolution_rate * 2), 0))
            self._open_incidents -= resolved
            self._resolved_incidents += resolved

            if resolved:
                logger.debug(
                    "Emergency tick: resolved %d incidents (open=%d)",
                    resolved,
                    self._open_incidents,
                )

    @property
    def open_incidents(self) -> int:
        return self._open_incidents

    @property
    def resolved_incidents(self) -> int:
        return self._resolved_incidents

