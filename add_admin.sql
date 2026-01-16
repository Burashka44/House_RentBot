-- Quick fix: Add admin user
-- Replace YOUR_TG_ID with your actual Telegram ID
-- Replace 'Your Name' with your actual name

INSERT INTO users (tg_id, full_name, role, is_active, created_at) 
VALUES (YOUR_TG_ID, 'Your Name', 'owner', true, NOW())
ON CONFLICT (tg_id) DO UPDATE SET role = 'owner', is_active = true;
