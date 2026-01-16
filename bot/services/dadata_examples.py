"""
Example: How to use DaData integration in bot handlers
"""

# ===== EXAMPLE 1: Autocomplete address in Telegram =====

async def handle_address_input(message: Message, state: FSMContext):
    """Handler when admin types address"""
    from bot.services.dadata_service import get_dadata_service
    
    user_input = message.text
    dadata = get_dadata_service()
    
    if not dadata:
        await message.answer("⚠️ DaData не настроен, используйте полный адрес")
        return
    
    # Get suggestions
    suggestions = await dadata.suggest_address(user_input, count=5)
    
    if not suggestions:
        await message.answer("❌ Адрес не найден. Попробуйте другой формат.")
        return
    
    # Show suggestions as inline keyboard
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = []
    for idx, sug in enumerate(suggestions):
        addr = sug['value']
        keyboard.append([
            InlineKeyboardButton(
                text=addr, 
                callback_data=f"select_addr_{idx}"
            )
        ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await state.update_data(address_suggestions=suggestions)
    await message.answer("📍 Выберите адрес:", reply_markup=kb)


async def handle_address_selected(call: CallbackQuery, state: FSMContext):
    """Handler when user selects address from suggestions"""
    from bot.services.address_service import NormalizedAddress
    
    idx = int(call.data.split("_")[-1])
    data = await state.get_data()
    suggestions = data.get("address_suggestions", [])
    
    if idx >= len(suggestions):
        await call.answer("Ошибка")
        return
    
    selected = suggestions[idx]
    addr_data = selected['data']
    
    # Create NormalizedAddress from DaData response
    normalized = NormalizedAddress(
        city=addr_data.get('city') or addr_data.get('settlement') or "Неизвестно",
        street=addr_data.get('street_with_type') or "Неизвестно",
        house_number=addr_data.get('house') or "0",
        region=addr_data.get('region_with_type')
    )
    
    # Also get UK if available
    uk_name = addr_data.get('management_company')
    
    await call.message.edit_text(
        f"✅ Адрес выбран:\n{selected['value']}\n\n"
        f"УК: {uk_name or 'Не указана'}"
    )
    
    # Save to state for next step
    await state.update_data(
        normalized_address=normalized,
        uk_name=uk_name,
        fias_id=addr_data.get('house_fias_id')
    )
    
    await call.answer()


# ===== EXAMPLE 2: Create House with DaData enrichment =====

async def create_house_from_dadata(session: AsyncSession, raw_address: str):
    """Create House in DB using DaData enriched data"""
    from bot.services.dadata_service import get_dadata_service
    from bot.database.models import House, UKCompany
    
    dadata = get_dadata_service()
    house_info = await dadata.get_house_info(raw_address)
    
    if not house_info:
        return None
    
    # Check if house already exists by FIAS ID
    fias_id = house_info.get('house_fias_id')
    if fias_id:
        stmt = select(House).where(House.fias_id == fias_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
    
    # Create or find UK
    uk_name = house_info.get('management_company')
    uk = None
    
    if uk_name:
        stmt = select(UKCompany).where(UKCompany.name.ilike(f"%{uk_name}%"))
        result = await session.execute(stmt)
        uk = result.scalar_one_or_none()
        
        if not uk:
            # Create new UK
            uk = UKCompany(name=uk_name)
            session.add(uk)
            await session.flush()
    
    # Create House
    house = House(
        region=house_info.get('region'),
        city=house_info.get('city'),
        street=house_info.get('street'),
        house_number=house_info.get('house'),
        postal_code=house_info.get('postal_code'),
        fias_id=fias_id,
        uk_id=uk.id if uk else None,
        geo_lat=house_info['coords'].get('lat') if house_info.get('coords') else None,
        geo_lon=house_info['coords'].get('lon') if house_info.get('coords') else None
    )
    
    session.add(house)
    await session.commit()
    
    return house


# ===== EXAMPLE 3: Get RSO by FIAS (if you implement GIS parser) =====

async def fetch_rso_for_house(fias_id: str) -> list:
    """
    Future: Fetch RSO providers from GIS ЖКХ using FIAS ID.
    
    This would require implementing gis_gkh_parser_service.py
    which we'll create in Option C.
    """
    # Placeholder for GIS ЖКХ parser
    pass
