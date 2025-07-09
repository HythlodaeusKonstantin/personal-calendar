#!/bin/bash

# Скрипт для генерации SSL сертификатов
# Запускать перед первым запуском приложения

echo "🔐 Генерация SSL сертификатов..."

# Проверяем, есть ли Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.8+"
    exit 1
fi

# Проверяем, есть ли cryptography
if ! python3 -c "import cryptography" &> /dev/null; then
    echo "📦 Установка cryptography..."
    pip3 install cryptography
fi

# Генерируем сертификаты
echo "🔑 Создание сертификатов..."
python3 generate_ssl.py

if [ $? -eq 0 ]; then
    echo "✅ SSL сертификаты созданы успешно!"
    echo "📁 Файлы:"
    echo "   - cert.pem (сертификат)"
    echo "   - key.pem (приватный ключ)"
    echo ""
    echo "🚀 Теперь можно запускать приложение:"
    echo "   docker compose up --build"
    echo ""
    echo "🌐 Приложение будет доступно по адресу:"
    echo "   https://localhost:8443"
else
    echo "❌ Ошибка при создании сертификатов"
    exit 1
fi 