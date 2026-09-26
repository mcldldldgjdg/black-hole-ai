#!/bin/bash
echo "🛑 Остановка Black Hole Studio AI..."

# Убиваем фоновые процессы
pkill -f uvicorn 2>/dev/null && echo "✅ Бэкенд остановлен" || echo "️  Бэкенд не был запущен"
pkill -f "http.server" 2>/dev/null && echo "✅ Фронтенд остановлен" || echo "⚠️  Фронтенд не был запущен"

# Останавливаем Docker
cd ~/black-hole-ai
docker-compose down 2>/dev/null && echo "✅ Ollama остановлена" || echo "⚠️  Docker не был запущен"

# Удаляем логи
rm -f backend.log frontend.log

echo " Всё остановлено!"
