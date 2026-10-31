# Обучение моделей на реальных интерьерах

Две модели дообучаются на фотографиях реальных квартир:

| Модель | Что даёт сайту | Метод |
|---|---|---|
| Stable Diffusion 1.5 + LoRA `bhs_interior` | визуализации и перерисовка фото похожи на реальные интерьеры | LoRA, kohya sd-scripts |
| Qwen2.5-3B-Instruct + адаптер → `bhs-designer` в Ollama | проекты комнат: реальные сочетания мебели, палитры, отделки | QLoRA (4 бита), PEFT |

## Данные

Фото — открытые лицензии (CC0, Public Domain, CC BY, CC BY-SA) через [Openverse](https://openverse.org).
Автор, лицензия и ссылка на оригинал каждого фото сохраняются в `data/photos.jsonl`.
Сами фото в репозиторий не кладутся (`data/` в `.gitignore`).

Разметка — `qwen2.5vl:3b` (через Ollama) описывает каждое фото: тип комнаты, стиль, мебель с материалами,
пол, стены, свет, концепцию. Палитра считается из пикселей фото (k-means), не моделью.

## Порядок запуска

Нужны: запущенный стек (`./start.sh`), Docker с доступом к GPU.

```bash
cd training
python3 -m venv .venv && .venv/bin/pip install httpx pillow numpy
docker build -t bhs-sd-lora -f docker/sd-lora.Dockerfile docker
docker build -t bhs-llm-lora -f docker/llm-lora.Dockerfile docker

.venv/bin/python collect_openverse.py          # фото → data/photos/, data/photos.jsonl
docker compose stop stable-diffusion           # освободить видеопамять для разметки
.venv/bin/python annotate.py                   # data/annotations.jsonl

.venv/bin/python make_sd_dataset.py            # data/sd/img/…  (картинки + подписи)
./train_sd_lora.sh                             # data/out/sd/bhs_interior.safetensors

.venv/bin/python make_llm_dataset.py           # data/llm/train.jsonl, val.jsonl
./train_llm_lora.sh                            # адаптер → GGUF → модель bhs-designer в Ollama
.venv/bin/python eval_llm.py                   # сравнение qwen2.5:3b и bhs-designer
```

Подключение к сайту: `./start.sh` сам берёт `bhs-designer`, если модель есть в Ollama,
и подключает LoRA из `data/out/sd/bhs_interior.safetensors`. Вернуть исходные модели:

```bash
OLLAMA_MODEL=qwen2.5:3b SD_STYLE_LORA= ./start.sh
```

## Результаты (31.10.2026)

Данные: 253 фото с Openverse → 247 размечено → 219 фото без людей для SD, 441/17 примеров (train/val) для Qwen.
Валидационные примеры — интерьеры, которых модель не видела при обучении.

**Qwen2.5-3B → bhs-designer** (2 эпохи, QLoRA r=16, ~55 мин на RTX 3070 Ti)

| | qwen2.5:3b | bhs-designer |
|---|---|---|
| eval loss на отложенных интерьерах | 0.85 | 0.31 |
| цены в реалистичном диапазоне | 7% | 100% |
| есть обязательная мебель | 94% | 100% |
| учтены пожелания к комнате | 100% | 88% |
| валидная палитра | 100% | 94% |
| валидный JSON / текст на русском | 100% / 100% | 100% / 100% |
| время ответа | 7.7 с | 6.1 с |

**SD 1.5 + LoRA bhs_interior** — выбрана версия после 2 эпох с весом 0.6 (`data/out/sd/compare_*.jpg`).
После 4 и 8 эпох LoRA переобучается: часть сцен вырождается в текстуру кирпичной стены.
Эффект умеренный: картинки ближе к реальным фото квартир (свет, материалы), но датасет маленький и разнородный.
В точечной перерисовке области LoRA не используется — она смещает цвета, которые пользователь задаёт сам.
