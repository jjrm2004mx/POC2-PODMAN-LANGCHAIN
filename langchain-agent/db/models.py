from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    domain: Mapped[Optional[str]] = mapped_column(String(50))
    category: Mapped[Optional[str]] = mapped_column(String(255))
    suggested_category: Mapped[Optional[str]] = mapped_column(String(255))
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[Optional[str]] = mapped_column(String(10))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    sender: Mapped[Optional[str]] = mapped_column(String(255))
    sender_name: Mapped[Optional[str]] = mapped_column(String(255))
    alert: Mapped[Optional[str]] = mapped_column(Text)
    external_ticket_id: Mapped[Optional[str]] = mapped_column(String(36))
    conversation_id: Mapped[Optional[str]] = mapped_column(String(200))
    email_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="ticket")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="ticket")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(36), unique=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tickets.id"))
    iterations_used: Mapped[Optional[int]] = mapped_column(Integer)
    is_validated: Mapped[Optional[bool]] = mapped_column(Boolean)
    provider: Mapped[Optional[str]] = mapped_column(String(50))
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ticket: Mapped[Optional["Ticket"]] = relationship(back_populates="agent_runs")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tickets.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    storage_key: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ticket: Mapped[Optional["Ticket"]] = relationship(back_populates="attachments")
