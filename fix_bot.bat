@echo off
echo ========================================
echo Fixing Bot Menu - Quick Setup
echo ========================================
echo.

set /p TG_ID="Enter your Telegram ID (send /id to bot): "

echo.
echo Adding you as admin to database...
docker-compose exec -T postgres psql -U postgres -d rent_bot -c "INSERT INTO users (tg_id, full_name, role, is_active) VALUES (%TG_ID%, 'Admin', 'owner', true) ON CONFLICT (tg_id) DO UPDATE SET role='owner', is_active=true;"

echo.
echo Restarting bot...
docker-compose restart bot

echo.
echo ========================================
echo DONE! Check Telegram - send /start
echo ========================================
pause
