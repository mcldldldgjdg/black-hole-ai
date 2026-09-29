#!/bin/bash
cd ~/black-hole-ai
echo "🛑 Остановка Black Hole Studio AI..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "✅ Бэкенд остановлен" || echo "⚠️  Бэкенд не был запущен"
docker-compose down 2>/dev/null && echo "✅ Ollama остановлена" || echo "️  Docker не был запущен"
rm -f backend.log
echo "✅ Всё остановлено!"
