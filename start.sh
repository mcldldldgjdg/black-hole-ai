#!/bin/bash
echo "🚀 Запуск Black Hole Studio AI..."

# Запуск Docker (Ollama)
echo " Запуск Ollama..."
docker-compose up -d

# Запуск бэкенда в фоне
echo "⚙️ Запуск бэкенда..."
cd backend
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Запуск фронтенда в фоне
echo "📁 Запуск фронтенда..."
nohup python3 -m http.server 3000 > frontend.log 2>&1 &
FRONTEND_PID=$!

echo "✅ Всё запущено!"
echo "   Фронтенд: http://localhost:3000/web2.html"
echo "   API: http://localhost:8000/docs"
echo "   PID бэкенда: $BACKEND_PID"
echo "   PID фронтенда: $FRONTEND_PID"
echo ""
echo "Для остановки: ./stop.sh"
