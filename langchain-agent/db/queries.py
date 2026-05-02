from datetime import datetime
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentRun, Attachment, Ticket


def _to_datetime(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


async def get_ticket_by_conversation_id(
    session: AsyncSession, conversation_id: str
) -> Optional[int]:
    result = await session.execute(
        select(Ticket.id).where(Ticket.conversation_id == conversation_id)
    )
    return result.scalar_one_or_none()


async def insert_ticket(
    session: AsyncSession,
    body: str,
    subject: Optional[str],
    domain: str,
    category: str,
    priority: str,
    confidence: float,
    source: Optional[str],
    sender: Optional[str],
    sender_name: Optional[str],
    alert: Optional[str],
    suggested_category: Optional[str],
    requires_review: bool,
    conversation_id: Optional[str],
    email_received_at=None,
) -> int:
    ticket = Ticket(
        body=body,
        subject=subject,
        domain=domain,
        category=category,
        priority=priority,
        confidence=confidence,
        source=source,
        sender=sender,
        sender_name=sender_name,
        alert=alert,
        suggested_category=suggested_category,
        requires_review=requires_review,
        conversation_id=conversation_id,
        email_received_at=_to_datetime(email_received_at),
    )
    session.add(ticket)
    await session.flush()
    return ticket.id


async def update_ticket_external_id(
    session: AsyncSession, ticket_id: int, external_id: str
) -> None:
    await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(external_ticket_id=external_id)
    )


async def insert_attachment(
    session: AsyncSession,
    ticket_id: int,
    filename: str,
    content_type: Optional[str],
) -> None:
    session.add(Attachment(ticket_id=ticket_id, filename=filename, content_type=content_type))


async def insert_agent_run(
    session: AsyncSession,
    run_id: str,
    ticket_id: Optional[int],
    iterations_used: int,
    is_validated: bool,
    provider: str,
    result: Optional[dict],
    duration_ms: int,
) -> None:
    session.add(
        AgentRun(
            run_id=run_id,
            ticket_id=ticket_id,
            iterations_used=iterations_used,
            is_validated=is_validated,
            provider=provider,
            result=result,
            duration_ms=duration_ms,
        )
    )
