"""P-11 Command Center persistence — dashboard-OWNED data only (§25).

The Command Center consumes the authoritative records of P-01–P-10 and must
never duplicate them. The only state the dashboard itself owns is:

* ``dashboard_preferences`` — per-principal UI preferences (sidebar state,
  default landing view, timezone/currency display choices). Presentation
  only; no operational meaning, no authority.
* ``dashboard_notification_states`` — per-principal read/dismiss markers for
  notifications that are DERIVED from existing records (approvals, security
  alerts, financial alerts, failed tasks, persisted events). The derived
  notification itself is never stored; only the owner's interaction state
  is, keyed by the deterministic notification id.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid, utcnow


class DashboardPreference(Base, TimestampMixin):
    __tablename__ = "dashboard_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # Principal key, e.g. "owner:owner" / "agent:<id>" — one row per principal.
    principal_key: Mapped[str] = mapped_column(
        String(232), nullable=False, unique=True, index=True)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DashboardNotificationState(Base, TimestampMixin):
    __tablename__ = "dashboard_notification_states"
    __table_args__ = (
        UniqueConstraint("principal_key", "notification_id",
                         name="uq_dashboard_notification_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    principal_key: Mapped[str] = mapped_column(String(232), nullable=False, index=True)
    # Deterministic derived-notification id, e.g. "approval:<uuid>".
    notification_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

    def mark_read(self) -> None:
        self.is_read = True
        self.read_at = utcnow()

    def mark_dismissed(self) -> None:
        self.is_dismissed = True
        self.dismissed_at = utcnow()
