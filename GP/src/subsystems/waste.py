"""Waste operations subsystem managing collection routes."""

from __future__ import annotations

import logging
import random
from collections import deque
from typing import Any, Deque

from src.subsystems.base import SubsystemThread

logger = logging.getLogger(__name__)


class WasteOps(SubsystemThread):
    """Simulate waste collection vehicle dispatch."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, config=config)
        cfg = config or {}
        self._fleet_size = cfg.get("fleet_size", 4)
        self._requests_per_tick = cfg.get("requests_per_tick", 5)
        self._rng = random.Random(cfg.get("seed"))
        self._pending_requests: Deque[int] = deque()
        self._served_requests = 0

    def execute_tick(self) -> None:
        new_requests = max(0, self._requests_per_tick + self._rng.randint(-2, 2))
        for _ in range(new_requests):
            self._pending_requests.append(self._rng.randint(1, 1000))

        active_fleet = min(self._fleet_size, len(self._pending_requests))
        for _ in range(active_fleet):
            self._pending_requests.popleft()
            self._served_requests += 1

        backlog = len(self._pending_requests)
        logger.debug(
            "Waste tick: new_requests=%d served=%d backlog=%d",
            new_requests,
            self._served_requests,
            backlog,
        )

    @property
    def backlog(self) -> int:
        return len(self._pending_requests)

    @property
    def served_requests(self) -> int:
        return self._served_requests

