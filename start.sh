#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "🚀 Запуск Black Hole Studio AI..."
echo ""

docker compose up -d ollama
until docker exec ollama-bhs ollama list >/dev/null 2>&1; do sleep 1; done

has_model() { docker exec ollama-bhs ollama list | awk 'NR>1 {print $1}' | grep -q "^$1\(:latest\)\?$"; }

if [ -z "$OLLAMA_MODEL" ]; then
    if has_model bhs-designer; then OLLAMA_MODEL=bhs-designer; else OLLAMA_MODEL=qwen2.5:3b; fi
fi
OLLAMA_VISION_MODEL="${OLLAMA_VISION_MODEL:-qwen2.5vl:3b}"
for m in "$OLLAMA_MODEL" "$OLLAMA_VISION_MODEL"; do
    has_model "$m" || { echo "⏳ Загрузка модели $m..."; docker exec ollama-bhs ollama pull "$m"; }
done

if [ -z "${SD_STYLE_LORA+x}" ] && [ -f training/data/out/sd/bhs_interior.safetensors ]; then
    SD_STYLE_LORA=bhs_interior
fi
export OLLAMA_MODEL OLLAMA_VISION_MODEL SD_STYLE_LORA

echo "🧠 Текстовая модель: $OLLAMA_MODEL"
echo "👁️  Модель зрения:   $OLLAMA_VISION_MODEL"
echo "🎨 LoRA для SD:     ${SD_STYLE_LORA:-нет}"
echo ""

docker compose up -d --build

if [ -n "$SD_STYLE_LORA" ] && [ -f "training/data/out/sd/$SD_STYLE_LORA.safetensors" ]; then
    docker cp "training/data/out/sd/$SD_STYLE_LORA.safetensors" stable-diffusion:/opt/stable-diffusion-webui/models/Lora/
fi

for _ in $(seq 1 30); do curl -sf http://localhost:8000/health >/dev/null && break; sleep 2; done
if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✅ Бэкенд запущен"
else
    echo "❌ Ошибка. Проверь: docker compose logs backend"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ВСЁ ЗАПУЩЕНО!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Сайт:     http://localhost:8000/"
echo "📍 API Docs: http://localhost:8000/docs"
echo "📍 SD WebUI: http://localhost:7860/ (первый запуск SD — несколько минут)"
echo ""
echo "💡 Для остановки: ./stop.sh"
echo "💡 Логи:          docker compose logs -f backend celery-worker"
echo ""
