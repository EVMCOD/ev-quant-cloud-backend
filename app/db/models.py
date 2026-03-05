from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Account(Base):
    """One row per MT5 EA / token."""

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    deliveries = relationship("Delivery", back_populates="account")
    group_memberships = relationship("GroupMember", back_populates="account")


class Group(Base):
    """Named group of accounts."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    members = relationship("GroupMember", back_populates="group")


class GroupMember(Base):
    """Many-to-many: Group <-> Account."""

    __tablename__ = "group_members"

    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)

    group = relationship("Group", back_populates="members")
    account = relationship("Account", back_populates="group_memberships")


class Signal(Base):
    """Signal received from TradingView."""

    __tablename__ = "signals"

    # TV-provided id is the PK (idempotency)
    id = Column(String(255), primary_key=True)
    strategy = Column(String(255), nullable=True)
    symbol = Column(String(50), nullable=False)
    action = Column(String(10), nullable=False)  # BUY / SELL
    risk_percent = Column(Float, nullable=False)
    sl_points = Column(Float, nullable=False)
    tp_points = Column(Float, nullable=False)
    is_broadcast = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    deliveries = relationship("Delivery", back_populates="signal")


class Delivery(Base):
    """
    One row per (signal, account) pair.
    status lifecycle: PENDING -> LEASED -> FILLED | REJECTED
    LEASED is a transient state held under FOR UPDATE SKIP LOCKED.
    """

    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(255), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    # PENDING -> LEASED -> DELIVERED -> FILLED | REJECTED
    status = Column(String(50), nullable=False, default="PENDING", index=True)

    leased_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    # Filled / rejected feedback from MT5
    ticket = Column(Integer, nullable=True)
    fill_price = Column(Float, nullable=True)
    slippage = Column(Float, nullable=True)
    reject_reason = Column(Text, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("signal_id", "account_id", name="uq_signal_account"),)

    signal = relationship("Signal", back_populates="deliveries")
    account = relationship("Account", back_populates="deliveries")
