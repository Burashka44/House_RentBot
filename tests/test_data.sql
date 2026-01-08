-- SQL Script to populate test data for UK/RSO system
-- Address: Сахалинская Область, г. Южно-Сахалинск, проспект Мира, 373А

-- 1. Create UK Company
INSERT INTO uk_companies (name, inn, phone, email, address, created_at, updated_at)
VALUES (
    'ООО "Управление ЖКХ Южно-Сахалинск"',
    '6501234567',
    '+7 (4242) 12-34-56',
    'uk@yuzhno.ru',
    'г. Южно-Сахалинск, ул. Ленина, 1',
    NOW(),
    NOW()
) RETURNING id;
-- Let's assume it returns id = 1

-- 2. Create House with UK link
INSERT INTO houses (region, city, street, house_number, uk_id, created_at, updated_at)
VALUES (
    'Сахалинская Область',
    'Южно-Сахалинск',
    'проспект Мира',  -- Note: case-sensitive, must match normalization output
    '373А',
    1,  -- UK company id from step 1
    NOW(),
    NOW()
);

-- 3. Create RSO Providers (will be linked to objects later)
-- Note: object_id is required, so we need to create a dummy object first
-- OR modify CommProvider model to make object_id nullable

-- For now, let's create RSO for demo (assuming object_id = 1 exists)
INSERT INTO comm_providers (object_id, service_type, name, short_keywords, account_number, active)
VALUES 
    (1, 'electric', 'РАО Энергетические системы Востока', '["рао", "энергия", "электр"]', '123456789', true),
    (1, 'water', 'МУП Водоканал Южно-Сахалинск', '["водоканал", "вода"]', '987654321', true),
    (1, 'heating', 'ПАО Сахалинская ТЭЦ', '["тэц", "тепло", "отопление"]', '555666777', true),
    (1, 'internet', 'Ростелеком Сахалин', '["ростелеком", "интернет"]', '111222333', true)
RETURNING id;
-- Let's assume they return ids 1, 2, 3, 4

-- 4. Link RSO to UK
INSERT INTO uk_rso_links (uk_id, provider_id, created_at, updated_at)
VALUES 
    (1, 1, NOW(), NOW()),  -- electric
    (1, 2, NOW(), NOW()),  -- water
    (1, 3, NOW(), NOW()),  -- heating
    (1, 4, NOW(), NOW());  -- internet


-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Check UK created
SELECT * FROM uk_companies;

-- Check House created with UK link
SELECT h.*, uk.name as uk_name 
FROM houses h 
LEFT JOIN uk_companies uk ON h.uk_id = uk.id
WHERE h.city = 'Южно-Сахалинск' AND h.house_number = '373А';

-- Check RSO linked to UK
SELECT uk.name as uk_name, cp.service_type, cp.name as provider_name
FROM uk_rso_links ukl
JOIN uk_companies uk ON ukl.uk_id = uk.id
JOIN comm_providers cp ON ukl.provider_id = cp.id
WHERE uk.id = 1;
