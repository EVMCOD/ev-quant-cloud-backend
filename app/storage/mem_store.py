from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
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

    # ✅ Broadcast: track delivery PER TOKEN
    delivered_to: Set[str] = field(default_factory=set)

    # Execution feedback (optional)
    ticket: Optional[int] = None
    fill_price: Optional[float] = None
    slippage: Optional[float] = None
    reject_reason: Optional[str] = None
    closed_at: Optional[float] = None


class MemStore:
    def __init__(self):
        self._signals: Dict[str, Signal] = {}
        self._queue: List[str] = []

    def add(self, s: Signal) -> bool:
        if s.id in self._signals:
            return False
        self._signals[s.id] = s
        self._queue.append(s.id)
        return True

    # ✅ Deliver once per token
    def pull_next_for_token(self, token: str) -> Optional[Signal]:
        token = (token or "").strip()
        if not token:
            return None

        for sid in list(self._queue):
            s = self._signals.get(sid)
            if not s:
                continue

            # already delivered to this token?
            if token in s.delivered_to:
                continue

            # deliver to this token
            s.delivered_to.add(token)
            s.status = "DELIVERED"
            s.delivered_at = time.time()
            return s

        return None

    # Keep for compatibility (single consumer)
    def pull_next(self) -> Optional[Signal]:
        return self.pull_next_for_token("__single__")

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