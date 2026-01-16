# Kvartplata APK Reverse Engineering Guide

## Необходимые инструменты

1. **JADX** (Java Decompiler)
   - Скачать: https://github.com/skylot/jadx/releases
   - Установка: распаковать ZIP

2. **APKTool** (Android APK Decompiler)
   - Скачать: https://apktool.org/
   
## Шаг 1: Получить APK

### Способ 1: С устройства (если приложение установлено)
```bash
# Через ADB
adb shell pm list packages | grep kvart
adb shell pm path com.fsgpay
adb pull /data/app/com.fsgpay-xxxxx/base.apk kvartplata.apk
```

### Способ 2: Из интернета
- APKPure: https://apkpure.com/search?q=kvartplata
- APKMirror: https://www.apkmirror.com/
- Искать: "Квартплата+ APK" или "com.fsgpay"

## Шаг 2: Декомпилировать с JADX

```bash
# Windows
jadx-gui.bat kvartplata.apk

# Linux/Mac
./jadx-gui kvartplata.apk
```

## Шаг 3: Поиск API ключей

### Что искать в коде:

1. **API Base URLs**
   ```java
   // Ищем строки типа:
   "https://lk.kvp24.ru"
   "kvartplata.ru"
   "api.kvp24.ru"
   ```

2. **API Keys / Tokens**
   ```java
   // Ищем переменные:
   API_KEY
   TOKEN
   CLIENT_ID
   CLIENT_SECRET
   Authorization
   Bearer
   ```

3. **HTTP Headers**
   ```java
   // Ищем использование:
   .header("X-Api-Key", ...)
   .header("Authorization", ...)
   addHeader(...)
   ```

4. **OAuth Config**
   ```java
   // Ищем:
   oauth
   client_credentials
   grant_type
   ```

### Типичные пути в декомпилированном коде:

```
com/fsgpay/
├── network/
│   ├── ApiClient.java          <- API конфигурация
│   ├── ApiService.java         <- Эндпоинты
│   └── AuthInterceptor.java    <- Токены/ключи
├── config/
│   └── AppConfig.java          <- Константы
└── BuildConfig.java            <- Build-time константы
```

## Шаг 4: Поиск через grep

После декомпиляции можно искать в исходниках:

```bash
# Поиск API ключей
grep -r "api.*key" .
grep -r "client.*secret" .
grep -r "Authorization" .
grep -r "Bearer" .

# Поиск URL
grep -r "kvp24.ru" .
grep -r "kvartplata.ru" .

# Поиск в ресурсах
grep -r "api_key" res/
```

## Шаг 5: Проверка strings.xml

```xml
<!-- res/values/strings.xml -->
<resources>
    <string name="api_base_url">https://lk.kvp24.ru</string>
    <string name="api_key">XXXXXXXXX</string>
</resources>
```

## Шаг 6: Использование найденных ключей

После нахождения токенов, добавить в запросы:

```python
headers = {
    "Authorization": "Bearer НАЙДЕННЫЙ_ТОКЕН",
    "X-Api-Key": "НАЙДЕННЫЙ_КЛЮЧ",
    "User-Agent": "Kvartplata Android/1.0",
}

async with session.get(url, headers=headers) as response:
    ...
```

## ⚠️ Важные замечания

1. **Обфускация**: Код может быть обфусцирован (ProGuard/R8)
   - Названия переменных: `a`, `b`, `c1`
   - Нужно анализировать логику

2. **Динамическая генерация**: Ключи могут генерироваться
   - Поиск алгоритмов генерации
   - Анализ native библиотек (.so файлы)

3. **Сертификат Pinning**: Приложение может проверять SSL сертификат
   - Нужен Frida/Xposed для bypass

4. **Ротация токенов**: Ключи могут обновляться
   - Интеграция станет нестабильной

## Альтернатива: Перехват трафика

Если ключи не найдены в коде, можно перехватить реальные запросы:

1. **Charles Proxy / Burp Suite**
2. **Frida** для bypass SSL Pinning
3. **Анализировать реальные HTTP заголовки**

## Следующий шаг

**Есть APK файл?**
- Да → Передайте путь к файлу
- Нет → Нужна помощь со скачиванием?
