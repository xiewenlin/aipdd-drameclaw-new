"""Project registry ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from novelvideo.db import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "name",
            name="uq_projects_owner_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner_username: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    home_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    output_dir: Mapped[str] = mapped_column(Text, nullable=False)
    state_dir: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_dir: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
