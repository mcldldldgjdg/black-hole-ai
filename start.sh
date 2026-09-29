#!/bin/bash
set -e
cd ~/black-hole-ai
echo "🚀 Запуск Black Hole Studio AI..."
echo "⚙️  Запуск Ollama (Docker)..."
docker-compose up -d
sleep 3
if docker ps | grep -q ollama-bhs; then echo "✅ Ollama запущена"; else echo "❌ Ошибка запуска Docker"; exit 1; fi
echo "⚙️  Запуск бэкенда (FastAPI)..."
cd backend && source venv/bin/activate
pkill -f "uvicorn main:app" 2>/dev/null || true
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
sleep 2
if curl -s http://localhost:8000/health > /dev/null; then echo "✅ Бэкенд запущен"; else echo " Ошибка запуска бэкенда. Проверь backend.log"; exit 1; fi
cd ..
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ВСЁ ЗАПУЩЕНО!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Сайт:     http://localhost:8000/"
echo "📍 API Docs: http://localhost:8000/docs"
echo " Health:   http://localhost:8000/health"
echo "💡 Для туннеля:   npx localtunnel --port 8000"
echo "💡 Для остановки: ./stop.sh"
