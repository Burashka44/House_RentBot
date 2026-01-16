from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.models import SupportMessage, Role, TenantStay

async def create_support_message(
    session: AsyncSession,
    stay_id: int,
    from_role: Role,
    text: str
) -> SupportMessage:
    msg = SupportMessage(
        stay_id=stay_id,
        from_role=from_role,
        text=text,
        is_read_by_admin=(from_role == Role.admin),
        is_read_by_tenant=(from_role == Role.tenant)
    )
    session.add(msg)
    await session.commit()
    return msg

async def get_chat_history(session: AsyncSession, stay_id: int):
    # Fetch last 50 messages
    stmt = select(SupportMessage).where(SupportMessage.stay_id == stay_id).order_by(SupportMessage.created_at.desc()).limit(50)
    result = await session.execute(stmt)
    return result.scalars().all()
