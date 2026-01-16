from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import UKRSOLink, ObjectRSOLink, CommProvider, UKCompany, CommServiceType

async def get_rso_by_uk(session: AsyncSession, uk_id: int) -> List[CommProvider]:
    """
    Get all RSO providers linked to a UK company.
    Returns list of CommProvider objects.
    """
    stmt = (
        select(CommProvider)
        .join(UKRSOLink, UKRSOLink.provider_id == CommProvider.id)
        .where(UKRSOLink.uk_id == uk_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_rso_by_object(session: AsyncSession, object_id: int) -> List[CommProvider]:
    """
    Get all RSO providers assigned to a specific object.
    Returns list of CommProvider objects.
    """
    stmt = (
        select(CommProvider)
        .join(ObjectRSOLink, ObjectRSOLink.provider_id == CommProvider.id)
        .where(ObjectRSOLink.object_id == object_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_object_rso_links(session: AsyncSession, object_id: int) -> List[ObjectRSOLink]:
    """
    Get all RSO links for an object, including provider details.
    """
    from sqlalchemy.orm import selectinload
    stmt = (
        select(ObjectRSOLink)
        .options(selectinload(ObjectRSOLink.provider))
        .where(ObjectRSOLink.object_id == object_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def assign_rso_to_object(
    session: AsyncSession, 
    object_id: int, 
    provider_ids: List[int],
    skip_duplicates: bool = True
) -> List[ObjectRSOLink]:
    """
    Assign RSO providers to an object.
    Creates ObjectRSOLink records.
    
    Args:
        object_id: Target rental object ID
        provider_ids: List of CommProvider IDs to assign
        skip_duplicates: If True, skip already assigned providers
    
    Returns:
        List of created ObjectRSOLink records
    """
    created_links = []
    
    for provider_id in provider_ids:
        # Check if link already exists
        if skip_duplicates:
            stmt = select(ObjectRSOLink).where(
                ObjectRSOLink.object_id == object_id,
                ObjectRSOLink.provider_id == provider_id
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                continue  # Skip duplicate
        
        # Create new link
        link = ObjectRSOLink(
            object_id=object_id,
            provider_id=provider_id
        )
        session.add(link)
        created_links.append(link)
    
    await session.commit()
    return created_links


async def remove_rso_from_object(
    session: AsyncSession, 
    object_id: int, 
    provider_id: int
) -> bool:
    """
    Remove RSO provider from an object.
    
    Returns:
        True if removed, False if not found
    """
    stmt = delete(ObjectRSOLink).where(
        ObjectRSOLink.object_id == object_id,
        ObjectRSOLink.provider_id == provider_id
    )
    result = await session.execute(stmt)
    await session.commit()
    
    return result.rowcount > 0


async def create_uk_rso_link(
    session: AsyncSession,
    uk_id: int,
    provider_id: int
) -> Optional[UKRSOLink]:
    """
    Create a link between UK company and RSO provider.
    Returns None if already exists.
    """
    # Check if exists
    stmt = select(UKRSOLink).where(
        UKRSOLink.uk_id == uk_id,
        UKRSOLink.provider_id == provider_id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        return None
    
    link = UKRSOLink(uk_id=uk_id, provider_id=provider_id)
    session.add(link)
    await session.commit()
    return link


async def update_rso_account_details(
    session: AsyncSession,
    object_id: int,
    provider_id: int,
    account_number: str
) -> bool:
    """
    Update the account number for a specific Object-RSO link.
    """
    stmt = select(ObjectRSOLink).where(
        ObjectRSOLink.object_id == object_id,
        ObjectRSOLink.provider_id == provider_id
    )
    result = await session.execute(stmt)
    link = result.scalar_one_or_none()
    
    if not link:
        return False
        
    link.account_number = account_number
    link.personal_account = account_number # Sync with new field
    await session.commit()
    return True

async def create_provider(
    session: AsyncSession,
    name: str,
    service_type: str,
    inn: Optional[str] = None
) -> CommProvider:
    """
    Create a new global RSO provider.
    """
    provider = CommProvider(
        name=name,
        service_type=service_type,
        inn=inn,
        object_id=None # Global provider
    )
    session.add(provider)
    await session.commit()
    return provider


async def get_all_rsos(session: AsyncSession) -> List[CommProvider]:
    """
    Get all RSO providers (CommProvider) in the system.
    """
    stmt = select(CommProvider).where(CommProvider.object_id == None)
    result = await session.execute(stmt)
    return list(result.scalars().all())
