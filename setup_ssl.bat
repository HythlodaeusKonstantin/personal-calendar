@echo off
echo 🔐 Генерация SSL сертификатов...

REM Проверяем, есть ли Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Установите Python 3.8+
    pause
    exit /b 1
)

REM Проверяем, есть ли cryptography
python -c "import cryptography" >nul 2>&1
if errorlevel 1 (
    echo 📦 Установка cryptography...
    pip install cryptography
)

REM Генерируем сертификаты
echo 🔑 Создание сертификатов...
python generate_ssl.py

if errorlevel 1 (
    echo ❌ Ошибка при создании сертификатов
    pause
    exit /b 1
) else (
    echo ✅ SSL сертификаты созданы успешно!
    echo 📁 Файлы:
    echo    - cert.pem (сертификат)
    echo    - key.pem (приватный ключ)
    echo.
    echo 🚀 Теперь можно запускать приложение:
    echo    docker compose up --build
    echo.
    echo 🌐 Приложение будет доступно по адресу:
    echo    https://localhost:8443
)

pause 