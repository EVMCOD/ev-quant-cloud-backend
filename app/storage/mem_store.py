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

    # Global status (for admin/overview)
    status: str = "PENDING"   # PENDING / ACTIVE / CLOSED
    closed_at: Optional[float] = None

    # Broadcast delivery tracking (per MT5 token)
    delivered_to: Set[str] = field(default_factory=set)
    delivered_at: Dict[str, float] = field(default_factory=dict)

    # Per-token execution feedback
    filled_by: Dict[str, Dict] = field(default_factory=dict)     # token -> {ticket, price, slippage, at}
    rejected_by: Dict[str, Dict] = field(default_factory=dict)   # token -> {reason, at}


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

    # Broadcast pull: returns next signal not yet delivered to this token
    def pull_next_for_token(self, token: str) -> Optional[Signal]:
        token = (token or "").strip()
        if not token:
            return None

        for sid in list(self._queue):
            s = self._signals.get(sid)
            if not s:
                continue

            # if this token already got it, skip
            if token in s.delivered_to:
                continue

            # deliver it to this token
            s.delivered_to.add(token)
            s.delivered_at[token] = time.time()

            # Mark as active once at least one delivery happens
            if s.status == "PENDING":
                s.status = "ACTIVE"

            return s

        return None

    # Keep old method for compatibility (single-consumer)
    def pull_next(self) -> Optional[Signal]:
        # Deprecated in broadcast mode; keep for backward compatibility.
        for sid in list(self._queue):
            s = self._signals.get(sid)
            if not s:
                continue
            # deliver to a synthetic token to ensure it doesn't re-deliver
            synthetic = "__single__"
            if synthetic in s.delivered_to:
                continue
            s.delivered_to.add(synthetic)
            s.delivered_at[synthetic] = time.time()
            if s.status == "PENDING":
                s.status = "ACTIVE"
            return s
        return None

    def ack_filled_for_token(self, token: str, signal_id: str, ticket: int, price: float, slippage: float | None):
        token = (token or "").strip()
        s = self._signals.get(signal_id)
        if not s or not token:
            return False

        s.filled_by[token] = {
            "ticket": int(ticket),
            "price": float(price),
            "slippage": float(slippage) if slippage is not None else None,
            "at": time.time(),
        }

        # If at least one fill happens you can consider it "ACTIVE" anyway.
        s.status = "ACTIVE"
        return True

    def ack_rejected_for_token(self, token: str, signal_id: str, reason: str):
        token = (token or "").strip()
        s = self._signals.get(signal_id)
        if not s or not token:
            return False

        s.rejected_by[token] = {
            "reason": reason or "UNKNOWN",
            "at": time.time(),
        }
        return True


STORE = MemStore()