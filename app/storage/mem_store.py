from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import time


@dataclass
class Signal:
    id: str
    strategy: str
    symbol: str
    action: str
    risk_percent: float
    sl_points: float
    tp_points: float
    created_at: float

    status: str = "PENDING"   # PENDING / DELIVERED / FILLED / REJECTED
    delivered_at: Optional[float] = None

    # Execution feedback
    ticket: Optional[int] = None
    fill_price: Optional[float] = None
    slippage: Optional[float] = None
    reject_reason: Optional[str] = None
    closed_at: Optional[float] = None  # time of ack


class MemStore:
    def __init__(self):
        self._signals: Dict[str, Signal] = {}
        self._queue: List[str] = []

    # Add new signal
    def add(self, s: Signal) -> bool:
        if s.id in self._signals:
            return False
        self._signals[s.id] = s
        self._queue.append(s.id)
        return True

    # Pull next pending signal (global queue)
    def pull_next(self) -> Optional[Signal]:
        for sid in list(self._queue):
            s = self._signals.get(sid)
            if not s:
                continue
            if s.status != "PENDING":
                continue

            s.status = "DELIVERED"
            s.delivered_at = time.time()
            return s

        return None

    # MT5-compatible wrapper (current version = shared queue)
    def pull_next_for_token(self, token: str) -> Optional[Signal]:
        # Token validation happens in mt5 route.
        # For now all tokens share the same queue.
        return self.pull_next()

    # Execution acknowledgements
    def ack_filled(self, signal_id: str, ticket: int, price: float, slippage: float | None):
        s = self._signals.get(signal_id)
        if not s:
            return False

        s.status = "FILLED"
        s.ticket = int(ticket)
        s.fill_price = float(price)
        s.slippage = float(slippage) if slippage is not None else None
        s.closed_at = time.time()
        return True

    def ack_rejected(self, signal_id: str, reason: str):
        s = self._signals.get(signal_id)
        if not s:
            return False

        s.status = "REJECTED"
        s.reject_reason = reason or "UNKNOWN"
        s.closed_at = time.time()
        return True


STORE = MemStore()